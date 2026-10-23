package local.diagnosis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.flowable.engine.HistoryService;
import org.flowable.engine.RepositoryService;
import org.flowable.engine.RuntimeService;
import org.flowable.engine.TaskService;
import org.flowable.engine.history.HistoricActivityInstance;
import org.flowable.engine.runtime.ProcessInstance;
import org.flowable.task.api.Task;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/diagnosis-api/instances/{instanceId}/review")
public class ReviewController {
    private final RuntimeService runtime;
    private final TaskService tasks;
    private final HistoryService history;
    private final RepositoryService repository;
    private final ObjectMapper json;

    public ReviewController(RuntimeService runtime, TaskService tasks, HistoryService history,
                            RepositoryService repository, ObjectMapper json) {
        this.runtime = runtime;
        this.tasks = tasks;
        this.history = history;
        this.repository = repository;
        this.json = json;
    }

    public record ReviewRequest(String action, String taskId, String targetNodeId, String reason,
                                Map<String, Object> variables) {}

    private JsonNode metadata(ProcessInstance instance) {
        String documentation = repository.getBpmnModel(instance.getProcessDefinitionId())
            .getMainProcess().getDocumentation();
        try {
            return documentation == null ? json.createObjectNode()
                : json.readTree(documentation).path("diagnosticExecution");
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

    private Task reviewTask(String instanceId, JsonNode metadata) {
        List<Task> pending = tasks.createTaskQuery().processInstanceId(instanceId).active().list();
        return pending.stream().filter(task -> metadata.path("reviews").has(task.getTaskDefinitionKey()))
            .findFirst().orElse(null);
    }

    private List<HistoricActivityInstance> visits(String instanceId) {
        return history.createHistoricActivityInstanceQuery().processInstanceId(instanceId)
            .activityType("externalWorkerServiceTask").finished()
            .orderByHistoricActivityInstanceStartTime().asc().list();
    }

    @GetMapping
    @Transactional(readOnly = true)
    public Map<String, Object> get(@PathVariable String instanceId) {
        ProcessInstance instance = runtime.createProcessInstanceQuery().processInstanceId(instanceId).singleResult();
        if (instance == null) return Map.of("pending", false);
        JsonNode metadata = metadata(instance);
        Task task = reviewTask(instanceId, metadata);
        if (task == null) return Map.of("pending", false);
        Map<String, JsonNode> bindings = bindings(metadata);
        Map<String, Object> candidates = new LinkedHashMap<>();
        for (HistoricActivityInstance visit : visits(instanceId)) {
            JsonNode binding = bindings.get(visit.getActivityId());
            if (binding != null && "investigation".equals(binding.path("kind").asText())) {
                candidates.put(visit.getActivityId(), Map.of("id", visit.getActivityId(),
                    "name", visit.getActivityName() == null ? visit.getActivityId() : visit.getActivityName()));
            }
        }
        return Map.of("pending", true, "taskId", task.getId(),
            "nodeId", metadata.path("reviews").path(task.getTaskDefinitionKey()).path("nodeId").asText(),
            "candidates", new ArrayList<>(candidates.values()));
    }

    @PostMapping
    @Transactional
    public Map<String, Object> act(@PathVariable String instanceId, @RequestBody ReviewRequest request) {
        ProcessInstance instance = runtime.createProcessInstanceQuery().processInstanceId(instanceId).singleResult();
        if (instance == null) throw new ResponseStatusException(HttpStatus.CONFLICT, "Process has ended / 流程已结束");
        JsonNode metadata = metadata(instance);
        Task task = reviewTask(instanceId, metadata);
        if (task == null) throw new ResponseStatusException(HttpStatus.CONFLICT, "No pending review / 当前不在复核状态");
        if (!task.getId().equals(request.taskId())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Review changed; refresh first / 复核状态已变更，请先刷新");
        }
        if (!"confirm".equals(request.action()) && !"recheck".equals(request.action())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown review action / 未知复核动作");
        }
        Map<String, JsonNode> bindings = bindings(metadata);
        List<HistoricActivityInstance> visits = visits(instanceId);
        Map<String, Object> variables = runtime.getVariables(instanceId);
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("id", UUID.randomUUID().toString());
        record.put("action", request.action());
        record.put("time", Instant.now().toString());
        record.put("from", task.getTaskDefinitionKey());
        record.put("reason", request.reason() == null ? "" : request.reason().trim());
        if ("recheck".equals(request.action())) {
            JsonNode target = bindings.get(request.targetNodeId());
            int targetVisit = -1;
            for (int index = 0; index < visits.size(); index++) {
                if (visits.get(index).getActivityId().equals(request.targetNodeId())) targetVisit = index;
            }
            if (target == null || !"investigation".equals(target.path("kind").asText()) || targetVisit < 0) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Choose a previously executed investigation / 请选择此前实际执行过的排查节点");
            }
            if (request.reason() == null || request.reason().isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A recheck reason is required / 必须填写回退原因");
            }
            Set<String> preserved = new LinkedHashSet<>();
            for (int index = 0; index < targetVisit; index++) preserved.add(visits.get(index).getActivityId());
            for (int index = targetVisit; index < visits.size(); index++) preserved.remove(visits.get(index).getActivityId());
            Set<String> cleared = new LinkedHashSet<>();
            for (String nodeId : bindings.keySet()) {
                if (!preserved.contains(nodeId)) {
                    cleared.add(nodeId);
                    cleared.add("route_" + nodeId);
                }
            }
            Map<String, Object> changes = request.variables() == null ? Map.of() : request.variables();
            for (String key : changes.keySet()) {
                if (bindings.containsKey(key) || key.startsWith("route_") || key.startsWith("diagnostic")) {
                    throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Cannot overwrite execution results or audit fields / 不可覆盖执行结果和复核记录");
                }
            }
            Map<String, Object> snapshot = new LinkedHashMap<>();
            for (String key : cleared) if (variables.containsKey(key)) snapshot.put(key, variables.get(key));
            Map<String, Object> previousInputs = new LinkedHashMap<>();
            for (String key : changes.keySet()) previousInputs.put(key, variables.get(key));
            record.put("target", request.targetNodeId());
            record.put("clearedResults", snapshot);
            record.put("previousInputs", previousInputs);
            record.put("inputChanges", changes);
            // 清理、记录与状态变更在同一事务中完成，worker 无法领取到半更新的重查任务。
            runtime.removeVariables(instanceId, cleared);
            changes.forEach((key, value) -> runtime.setVariable(instanceId, key, json.valueToTree(value)));
        }
        List<Object> records = new ArrayList<>();
        Object existing = variables.get("diagnosticReviews");
        if (existing instanceof JsonNode node && node.isArray()) node.forEach(records::add);
        records.add(record);
        runtime.setVariable(instanceId, "diagnosticReviews", json.valueToTree(records));
        if ("confirm".equals(request.action())) {
            tasks.complete(task.getId());
        } else {
            runtime.createChangeActivityStateBuilder().processInstanceId(instanceId)
                .moveActivityIdTo(task.getTaskDefinitionKey(), request.targetNodeId()).changeState();
        }
        return Map.of("ok", true, "action", request.action());
    }
}
