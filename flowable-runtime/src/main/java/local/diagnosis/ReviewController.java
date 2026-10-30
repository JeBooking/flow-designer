package local.diagnosis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.flowable.common.engine.api.FlowableObjectNotFoundException;
import org.flowable.common.engine.api.FlowableOptimisticLockingException;
import org.flowable.engine.HistoryService;
import org.flowable.engine.ManagementService;
import org.flowable.engine.RepositoryService;
import org.flowable.engine.RuntimeService;
import org.flowable.engine.TaskService;
import org.flowable.engine.history.HistoricActivityInstance;
import org.flowable.engine.runtime.ProcessInstance;
import org.flowable.task.api.Task;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/diagnosis-api/instances/{instanceId}/review")
public class ReviewController {
    private final RuntimeService runtime;
    private final TaskService tasks;
    private final HistoryService history;
    private final ManagementService management;
    private final RepositoryService repository;
    private final ObjectMapper json;

    public ReviewController(RuntimeService runtime, TaskService tasks, HistoryService history, ManagementService management,
                            RepositoryService repository, ObjectMapper json) {
        this.runtime = runtime;
        this.tasks = tasks;
        this.history = history;
        this.management = management;
        this.repository = repository;
        this.json = DiagnosticJson.configure(json);
    }

    public record ReviewRequest(String action, String taskId, String targetNodeId, String reason,
                                Map<String, Object> variables, String next, List<String> selectedFlowIds) {}

    private JsonNode metadata(ProcessInstance instance) {
        try {
            return DiagnosticMetadata.read(repository, instance.getProcessDefinitionId(), json);
        } catch (Exception ignored) {
            return json.createObjectNode();
        }
    }

    private Map<String, JsonNode> bindings(JsonNode metadata) {
        Map<String, JsonNode> result = new LinkedHashMap<>();
        metadata.path("bindings").elements().forEachRemaining(binding ->
            result.put(binding.path("nodeId").asText(), binding));
        return result;
    }

    private List<Task> reviewTasks(String instanceId, JsonNode metadata) {
        List<Task> pending = tasks.createTaskQuery().processInstanceId(instanceId).active().list();
        return pending.stream().filter(task -> metadata.path("reviews").has(task.getTaskDefinitionKey()))
            .sorted(Comparator.comparing(Task::getCreateTime, Comparator.nullsLast(Comparator.naturalOrder()))
                .thenComparing(Task::getId))
            .toList();
    }

    private List<HistoricActivityInstance> visits(String instanceId) {
        return history.createHistoricActivityInstanceQuery().processInstanceId(instanceId)
            .finished().orderByHistoricActivityInstanceStartTime().asc().list().stream()
            .filter(visit -> Set.of("externalWorkerServiceTask", "userTask").contains(visit.getActivityType()))
            .toList();
    }

    private String nodeId(HistoricActivityInstance visit, JsonNode metadata) {
        return metadata.path("reviews").path(visit.getActivityId()).path("nodeId")
            .asText(visit.getActivityId());
    }

    private ObjectNode instructions(JsonNode review, Object componentRequest) {
        ObjectNode result = review.path("instructions").isObject()
            ? ((ObjectNode) review.path("instructions")).deepCopy() : json.createObjectNode();
        JsonNode request = json.valueToTree(componentRequest);
        if (!request.path("instructions").asText().isBlank()) {
            result.put("assessment", request.path("instructions").asText());
        }
        return result;
    }

    private boolean internalVariable(String key) {
        return key.startsWith("executionTrace_") || key.startsWith("diagnostic")
            || key.startsWith("pythonSession_") || key.startsWith("route_")
            || key.startsWith("pythonCheckpoint_")
            || key.startsWith("human_") || key.startsWith("request_")
            || key.startsWith("selectedRoutes_");
    }

    private JsonNode inputs(Map<String, Object> variables) {
        Map<String, Object> context = new LinkedHashMap<>();
        variables.forEach((key, value) -> {
            if (!internalVariable(key)) context.put(key, value);
        });
        // 这是人工决策时可见的业务上下文，不代表 Python 函数实际收到的参数。
        return json.valueToTree(context);
    }

    @GetMapping
    @Transactional(readOnly = true)
    public Map<String, Object> get(@PathVariable String instanceId) {
        List<Map<String, Object>> pending = pendingReviews(instanceId);
        return pending.isEmpty() ? Map.of("pending", false) : pending.get(0);
    }

    @GetMapping("/tasks")
    @Transactional(readOnly = true)
    public Map<String, Object> getTasks(@PathVariable String instanceId) {
        return Map.of("tasks", pendingReviews(instanceId));
    }

    private List<Map<String, Object>> pendingReviews(String instanceId) {
        ProcessInstance instance = runtime.createProcessInstanceQuery().processInstanceId(instanceId).singleResult();
        if (instance == null) return List.of();
        JsonNode metadata = metadata(instance);
        List<Task> pending = reviewTasks(instanceId, metadata);
        if (pending.isEmpty()) return List.of();
        Map<String, Object> variables = runtime.getVariables(instanceId);
        List<HistoricActivityInstance> visits = visits(instanceId);
        boolean canRecheck = !"parallel".equals(metadata.path("mode").asText()) || pending.size() == 1;
        return pending.stream().map(task -> reviewState(task, metadata, variables, visits, canRecheck)).toList();
    }

    private Map<String, Object> reviewState(Task task, JsonNode metadata,
                                           Map<String, Object> variables,
                                           List<HistoricActivityInstance> visits, boolean canRecheck) {
        Map<String, JsonNode> bindings = bindings(metadata);
        JsonNode review = metadata.path("reviews").path(task.getTaskDefinitionKey());
        String currentNode = review.path("nodeId").asText();
        ObjectNode instructions = instructions(review, variables.get("request_" + currentNode));
        Map<String, Object> candidates = new LinkedHashMap<>();
        for (HistoricActivityInstance visit : visits) {
            String id = nodeId(visit, metadata);
            if (bindings.containsKey(id) && !id.equals(currentNode)) {
                candidates.putIfAbsent(id, Map.of("id", id,
                    "name", visit.getActivityName() == null ? id : visit.getActivityName()));
            }
        }
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("pending", true);
        state.put("taskId", task.getId());
        state.put("nodeId", currentNode);
        state.put("mode", review.path("mode").asText("escalation"));
        state.put("actionMode", review.path("actionMode").asText());
        state.put("kind", metadata.path("nodes").path(currentNode).path("kind").asText());
        // 同一节点可有多个并行待办，只显示当前 task 的最近一次动作核验。
        JsonNode records = json.valueToTree(variables.get("diagnosticReviews"));
        if (records.isArray()) {
            for (JsonNode record : records) {
                if (task.getId().equals(record.path("taskId").asText())
                    && "action".equals(record.path("mode").asText())
                    && Set.of("ok", "not_ok").contains(record.path("actionResult").asText())) {
                    state.put("lastActionResult", record.path("actionResult").asText());
                }
            }
        }
        state.put("name", review.path("name").asText(task.getName()));
        state.put("selectionMode", "single");
        state.put("canRecheck", canRecheck);
        state.put("options", review.path("options").isArray() ? review.path("options") : json.createArrayNode());
        state.put("instructions", instructions);
        state.put("evidence", json.valueToTree(variables.get(currentNode)));
        state.put("inputs", inputs(variables));
        state.put("candidates", new ArrayList<>(candidates.values()));
        return state;
    }

    @PostMapping
    @Transactional
    public Map<String, Object> act(@PathVariable String instanceId, @RequestBody ReviewRequest request) {
        // Spring 事务不共享各次引擎调用的实体缓存；统一命令上下文才能让快照与写回使用同一版本，
        // 并发提交时由乐观锁回滚整个复核，避免任务完成但审计数组被旧快照覆盖。
        return management.executeCommand(context -> applyReview(instanceId, request));
    }

    private Map<String, Object> applyReview(String instanceId, ReviewRequest request) {
        ProcessInstance instance = runtime.createProcessInstanceQuery().processInstanceId(instanceId).singleResult();
        if (instance == null) throw new ResponseStatusException(HttpStatus.CONFLICT, "Process has ended / 流程已结束");
        JsonNode metadata = metadata(instance);
        if (request.taskId() == null || request.taskId().isBlank()) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Review task is required; refresh first / 缺少复核任务，请先刷新");
        }
        Task task = tasks.createTaskQuery().processInstanceId(instanceId)
            .taskId(request.taskId()).active().singleResult();
        if (task == null || !metadata.path("reviews").has(task.getTaskDefinitionKey())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Review changed; refresh first / 复核状态已变更，请先刷新");
        }
        if (!"confirm".equals(request.action()) && !"recheck".equals(request.action())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown review action / 未知复核动作");
        }
        // 现有重查会清理全局业务结果，多个人工分支等待时不能破坏其他窗口的决策依据。
        if ("recheck".equals(request.action()) && "parallel".equals(metadata.path("mode").asText())
            && reviewTasks(instanceId, metadata).size() > 1) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Complete the other pending reviews before rechecking / 请先处理其余人工任务，再发起重查");
        }
        Map<String, JsonNode> bindings = bindings(metadata);
        JsonNode review = metadata.path("reviews").path(task.getTaskDefinitionKey());
        String currentNode = review.path("nodeId").asText();
        List<HistoricActivityInstance> visits = visits(instanceId);
        Map<String, Object> variables = runtime.getVariables(instanceId);
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("id", UUID.randomUUID().toString());
        record.put("action", request.action());
        record.put("time", Instant.now().toString());
        record.put("from", task.getTaskDefinitionKey());
        record.put("nodeId", currentNode);
        record.put("taskId", task.getId());
        record.put("mode", review.path("mode").asText("escalation"));
        record.put("actionMode", review.path("actionMode").asText());
        record.put("kind", metadata.path("nodes").path(currentNode).path("kind").asText());
        // 必须在回退清理或人工覆盖结果之前冻结依据，避免后续模型变化改写历史。
        record.put("inputs", inputs(variables));
        record.put("evidence", json.valueToTree(variables.get(currentNode)));
        record.put("instructions", instructions(review, variables.get("request_" + currentNode)));
        record.put("reason", request.reason() == null ? "" : request.reason().trim());
        if ("recheck".equals(request.action()) && "success".equals(review.path("mode").asText())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Success review supports continue or finish / 成功后请选择继续或结束排查");
        }
        if ("recheck".equals(request.action())) {
            JsonNode target = bindings.get(request.targetNodeId());
            int targetVisit = -1;
            for (int index = 0; index < visits.size(); index++) {
                if (nodeId(visits.get(index), metadata).equals(request.targetNodeId())) targetVisit = index;
            }
            if (target == null || targetVisit < 0 || currentNode.equals(request.targetNodeId())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Choose a previously executed node / 请选择此前实际执行过的节点");
            }
            if (request.reason() == null || request.reason().isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A recheck reason is required / 必须填写回退原因");
            }
            Set<String> preserved = new LinkedHashSet<>();
            for (int index = 0; index < targetVisit; index++) preserved.add(nodeId(visits.get(index), metadata));
            for (int index = targetVisit; index < visits.size(); index++) preserved.remove(nodeId(visits.get(index), metadata));
            Set<String> cleared = new LinkedHashSet<>();
            for (String nodeId : bindings.keySet()) {
                if (!preserved.contains(nodeId)) {
                    cleared.add(nodeId);
                    cleared.add("route_" + nodeId);
                    cleared.add("human_" + nodeId);
                    cleared.add("request_" + nodeId);
                    cleared.add("selectedRoutes_" + nodeId);
                }
            }
            Map<String, Object> changes = request.variables() == null ? Map.of() : request.variables();
            for (String key : changes.keySet()) {
                if (bindings.containsKey(key) || internalVariable(key)) {
                    throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Cannot overwrite execution results or audit fields / 不可覆盖执行结果和复核记录");
                }
            }
            Map<String, Object> snapshot = new LinkedHashMap<>();
            for (String key : cleared) if (variables.containsKey(key)) snapshot.put(key, variables.get(key));
            Map<String, Object> previousInputs = new LinkedHashMap<>();
            for (String key : changes.keySet()) previousInputs.put(key, variables.get(key));
            record.put("target", request.targetNodeId());
            record.put("clearedResults", json.valueToTree(snapshot));
            record.put("previousInputs", json.valueToTree(previousInputs));
            record.put("inputChanges", json.valueToTree(changes));
            // 清理、记录与状态变更在同一事务中完成，worker 无法领取到半更新的重查任务。
            runtime.removeVariables(instanceId, cleared);
            changes.forEach((key, value) -> runtime.setVariable(instanceId, key, json.valueToTree(value)));
        } else if ("action".equals(review.path("mode").asText())) {
            if (!Set.of("ok", "not_ok").contains(request.next() == null ? "" : request.next())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Choose OK or not OK / 请选择执行结果 OK 或不 OK");
            }
            Object previousResult = variables.get(currentNode);
            record.put("previousResult", json.valueToTree(previousResult));
            record.put("actionResult", request.next());
            record.put("next", request.next());
            JsonNode previous = json.valueToTree(previousResult);
            ObjectNode result = previous.isObject() ? ((ObjectNode) previous).deepCopy()
                : json.createObjectNode();
            if (previousResult != null && !previous.isObject()) result.set("data", previous);
            // 动作核验只补充人工结果，保留 Python 的 success/next 等原始执行语义。
            result.put("humanConfirmed", "ok".equals(request.next()));
            result.put("actionResult", request.next());
            runtime.setVariable(instanceId, currentNode, result);
        } else if ("success".equals(review.path("mode").asText())) {
            if (!Set.of("continue", "finish").contains(request.next() == null ? "" : request.next())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Choose continue or finish / 请选择继续或结束排查");
            }
            record.put("next", request.next());
            record.put("remainingQueue", json.valueToTree(variables.get("diagnosticQueue")));
            runtime.setVariable(instanceId, "diagnosticContinue", "continue".equals(request.next()));
        } else if ("decision".equals(review.path("mode").asText())) {
            List<String> options = new ArrayList<>();
            review.path("options").forEach(option -> options.add(option.path("id").asText()));
            String next = request.next();
            if (options.size() == 1 && (next == null || next.isBlank())) next = options.get(0);
            if ((!options.isEmpty() && !options.contains(next)) ||
                (options.isEmpty() && next != null && !next.isBlank())) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Choose a valid outgoing option / 请选择有效的后继选项");
            }
            Set<String> allowedFlowIds = new LinkedHashSet<>();
            for (JsonNode edge : metadata.path("nodes").path(currentNode).path("outgoing")) {
                if (edge.path("branch").asText().equals(next)) allowedFlowIds.add(edge.path("id").asText());
            }
            // 旧客户端未传子集时保留整组语义；显式选择必须属于当前是/否分组。
            List<String> selectedFlowIds = request.selectedFlowIds() == null
                ? new ArrayList<>(allowedFlowIds) : request.selectedFlowIds();
            Set<String> uniqueFlowIds = new LinkedHashSet<>(selectedFlowIds);
            if (uniqueFlowIds.size() != selectedFlowIds.size()
                || !allowedFlowIds.containsAll(uniqueFlowIds)
                || !allowedFlowIds.isEmpty() && selectedFlowIds.isEmpty()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Choose one or more unique paths from the selected branch / 请在所选是或否分组内选择至少一条不重复的后续思路");
            }
            ObjectNode selectedRoutes = json.createObjectNode();
            selectedFlowIds.forEach(flowId -> selectedRoutes.put(flowId, true));
            boolean parallel = "parallel".equals(metadata.path("mode").asText());
            // 并行 token 可能复用同一原节点，分支选择必须跟随当前 execution，避免互相覆盖。
            if (parallel) runtime.setVariableLocal(task.getExecutionId(), "selectedRoutes_" + currentNode, selectedRoutes);
            else runtime.setVariable(instanceId, "selectedRoutes_" + currentNode, selectedRoutes);
            // 保留 Python 原始建议用于追溯；当前节点结果的 next 与人工实际选择保持一致。
            Object previousResult = variables.get(currentNode);
            record.put("previousResult", json.valueToTree(previousResult));
            record.put("next", next);
            record.put("selectedFlowIds", List.copyOf(selectedFlowIds));
            var result = previousResult instanceof JsonNode value && value.isObject()
                ? ((com.fasterxml.jackson.databind.node.ObjectNode) value).deepCopy()
                : json.createObjectNode();
            if (previousResult != null && !(previousResult instanceof JsonNode value && value.isObject())) {
                result.set("data", json.valueToTree(previousResult));
            }
            if (next != null) result.put("next", next);
            result.put("humanConfirmed", true);
            result.set("selectedFlowIds", json.valueToTree(selectedFlowIds));
            runtime.setVariable(instanceId, currentNode, result);
            if (options.size() > 1) {
                if (parallel) runtime.setVariableLocal(task.getExecutionId(), "route_" + currentNode, next);
                else runtime.setVariable(instanceId, "route_" + currentNode, next);
            }
        }
        List<Object> records = new ArrayList<>();
        Object existing = variables.get("diagnosticReviews");
        if (existing instanceof JsonNode node && node.isArray()) node.forEach(records::add);
        records.add(record);
        runtime.setVariable(instanceId, "diagnosticReviews", json.valueToTree(records));
        boolean actionReview = "action".equals(review.path("mode").asText())
            && "confirm".equals(request.action());
        // 不 OK 保留原待办及 token，后续人工重做后可再次核验，不重跑 Python 或消耗串行队列。
        if (actionReview && "not_ok".equals(request.next())) {
            return Map.of("ok", true, "pending", true, "actionResult", "not_ok");
        }
        if ("confirm".equals(request.action())) {
            tasks.complete(task.getId());
        } else {
            runtime.createChangeActivityStateBuilder().processInstanceId(instanceId)
                .moveExecutionToActivityId(task.getExecutionId(), request.targetNodeId()).changeState();
        }
        if (actionReview) return Map.of("ok", true, "pending", false, "actionResult", "ok");
        return Map.of("ok", true, "action", request.action());
    }

    // 提交与事务提交阶段都可能遇到并行更新；交由 MVC 在事务回滚后统一返回可刷新重试的状态。
    @ExceptionHandler({FlowableOptimisticLockingException.class, OptimisticLockingFailureException.class,
        FlowableObjectNotFoundException.class})
    public ResponseEntity<Map<String, Object>> reviewConflict(Exception error) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("ok", false,
            "error", "Review changed during submission; refresh and retry / 提交期间复核状态已变更，请刷新后重试"));
    }
}
