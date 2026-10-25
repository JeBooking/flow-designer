package local.diagnosis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import org.flowable.engine.delegate.DelegateExecution;
import org.flowable.engine.delegate.ExecutionListener;
import org.flowable.engine.delegate.JavaDelegate;
import org.flowable.common.engine.api.delegate.Expression;

/** 原业务节点仍由引擎执行，持久队列仅控制串行思路的领取顺序。 */
public class DiagnosisScheduler implements JavaDelegate, ExecutionListener {
    private static final ObjectMapper JSON = new ObjectMapper();
    private Expression source;
    private Expression operation;

    public void setSource(Expression value) { source = value; }
    public void setOperation(Expression value) { operation = value; }

    private JsonNode metadata(DelegateExecution execution) {
        var process = org.flowable.engine.impl.util.CommandContextUtil.getProcessEngineConfiguration().getRepositoryService()
            .getBpmnModel(execution.getProcessDefinitionId()).getMainProcess();
        try {
            return JSON.readTree(process.getExtensionElements().get("diagnosticExecution")
                .get(0).getAttributes().get("value").get(0).getValue());
        } catch (Exception error) {
            throw new IllegalStateException("Missing diagnostic execution metadata", error);
        }
    }

    private ArrayNode array(Object value) {
        JsonNode node = JSON.valueToTree(value);
        return node != null && node.isArray() ? ((ArrayNode) node).deepCopy() : JSON.createArrayNode();
    }

    @Override public void notify(DelegateExecution execution) { execute(execution); }

    @Override public void execute(DelegateExecution execution) {
        String nodeId = String.valueOf(source.getValue(execution));
        String action = String.valueOf(operation.getValue(execution));
        JsonNode manifest = metadata(execution);
        JsonNode node = manifest.path("nodes").path(nodeId);
        boolean serial = "serial".equals(manifest.path("mode").asText());
        if ("visit".equals(action)) {
            JsonNode previous = JSON.valueToTree(execution.getVariable("diagnosticSteps"));
            int steps = previous == null ? 1 : previous.asInt() + 1;
            JsonNode limit = JSON.valueToTree(execution.getVariable("diagnosticMaxSteps"));
            if (steps > (limit == null ? 1000 : limit.asInt(1000))) {
                throw new IllegalStateException("Maximum diagnostic steps exceeded / 超过最大排查步数");
            }
            execution.setVariable("diagnosticSteps", steps);
            ArrayNode path = array(execution.getVariable("diagnosticPath"));
            path.add(nodeId);
            // 并行分支各自保存路径，避免兄弟分支覆盖失败记录的来源。
            if (serial) execution.setVariable("diagnosticPath", path);
            else execution.setVariableLocal("diagnosticPath", path);
            return;
        }
        if ("initialize".equals(action)) {
            execution.setVariable("diagnosticStatus", "running");
            return;
        }
        if ("complete".equals(action)) {
            // 只有所有并行 token 都结束，才能把单思路失败汇总为整次排查失败。
            String status = Boolean.TRUE.equals(execution.getVariable("diagnosticHasSuccess")) ? "problemSolved"
                : execution.getVariable("diagnosticHandoff") != null ? String.valueOf(execution.getVariable("diagnosticHandoff")) : "failed";
            execution.setVariable("diagnosticStatus", status);
            return;
        }
        if ("failure".equals(action)) {
            failure(execution, nodeId);
            return;
        }
        if ("success".equals(action)) {
            execution.setVariable("diagnosticHasSuccess", true);
            execution.setVariable("diagnosticStatus", "problemSolved");
            return;
        }
        if ("outcome".equals(action)) {
            String outcome = node.path("kind").asText();
            if (!"escalation".equals(execution.getVariable("diagnosticHandoff"))) {
                execution.setVariable("diagnosticHandoff", outcome);
            }
            if (!Boolean.TRUE.equals(execution.getVariable("diagnosticHasSuccess"))) {
                execution.setVariable("diagnosticStatus", execution.getVariable("diagnosticHandoff"));
            }
            return;
        }
        ArrayNode queue = array(execution.getVariable("diagnosticQueue"));
        String kind = node.path("kind").asText();
        if ("resume".equals(action)) {
            boolean proceed = Boolean.TRUE.equals(execution.getVariable("diagnosticContinue"));
            execution.removeVariable("diagnosticContinue");
            if (!proceed) queue.removeAll();
        } else if ("problemSolved".equals(kind)) {
            execution.setVariable("diagnosticHasSuccess", true);
            if (!queue.isEmpty()) {
                execution.setVariable("diagnosticQueue", queue);
                execution.setVariable("diagnosticStatus", "paused");
                execution.setVariable("diagnosticNext", node.path("successReview").asText());
                return;
            }
        } else if ("escalation".equals(kind) || "jump".equals(kind) && node.path("outgoing").isEmpty()) {
            execution.setVariable("diagnosticHandoff", kind);
        } else {
            ArrayNode targets = JSON.createArrayNode();
            String branch = String.valueOf(execution.getVariable("route_" + nodeId));
            for (JsonNode edge : node.path("outgoing")) {
                if (!"investigation".equals(kind) || edge.path("branch").asText().equals(branch)) {
                    ObjectNode entry = JSON.createObjectNode();
                    entry.put("node", edge.path("target").asText());
                    entry.set("path", array(execution.getVariable("diagnosticPath")));
                    targets.add(entry);
                }
            }
            if (targets.isEmpty() && "investigation".equals(kind)) failure(execution, nodeId);
            // 深度优先队列保留当前 fork 的剩余思路；恢复不会重新生成已经领取的兄弟。
            ArrayNode combined = JSON.createArrayNode();
            combined.addAll(targets);
            combined.addAll(queue);
            queue = combined;
        }
        if (!queue.isEmpty()) {
            JsonNode next = queue.remove(0);
            execution.setVariable("diagnosticPath", next.path("path"));
            execution.setVariable("diagnosticNext", next.path("node").asText());
            execution.setVariable("diagnosticStatus", "running");
        } else {
            execution.setVariable("diagnosticNext", manifest.path("endId").asText());
            String status = Boolean.TRUE.equals(execution.getVariable("diagnosticHasSuccess")) ? "problemSolved"
                : execution.getVariable("diagnosticHandoff") != null ? String.valueOf(execution.getVariable("diagnosticHandoff")) : "failed";
            execution.setVariable("diagnosticStatus", status);
        }
        execution.setVariable("diagnosticQueue", queue);
    }

    private void failure(DelegateExecution execution, String nodeId) {
        ArrayNode failures = array(execution.getVariable("diagnosticFailures"));
        ObjectNode record = JSON.createObjectNode();
        record.put("node", nodeId);
        record.put("nodeId", nodeId);
        record.set("result", JSON.valueToTree(execution.getVariable(nodeId)));
        record.put("branch", String.valueOf(execution.getVariable("route_" + nodeId)));
        record.put("reason", "No matching outgoing branch / 判断结果没有匹配出口");
        record.set("path", array(execution.getVariable("diagnosticPath")));
        record.put("time", Instant.now().toString());
        failures.add(record);
        execution.setVariable("diagnosticFailures", failures);
    }
}
