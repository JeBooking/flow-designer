package local.diagnosis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.flowable.common.engine.impl.db.HasRevision;
import org.flowable.common.engine.api.query.QueryProperty;
import org.flowable.engine.HistoryService;
import org.flowable.engine.ManagementService;
import org.flowable.engine.RepositoryService;
import org.flowable.engine.TaskService;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ExecutionHistoryController {
    private final HistoryService history;
    private final ManagementService management;
    private final RepositoryService repository;
    private final TaskService tasks;
    private final ObjectMapper json;
    private final Map<String, DefinitionSummary> summaries = new LinkedHashMap<>();
    private static final QueryProperty HISTORY_ID = () -> "ID_";
    private record DefinitionSummary(String version, List<Map<String, String>> nodes) {}

    public ExecutionHistoryController(HistoryService history, ManagementService management,
                                      RepositoryService repository, TaskService tasks, ObjectMapper json) {
        this.history = history;
        this.management = management;
        this.repository = repository;
        this.tasks = tasks;
        this.json = DiagnosticJson.configure(json);
    }

    public record HistoryRequest(Map<String, Integer> variables, Map<String, String> activities) {}

    private DefinitionSummary summary(String definitionId) {
        synchronized (summaries) {
            if (summaries.containsKey(definitionId)) return summaries.get(definitionId);
        }
        JsonNode metadata;
        try {
            metadata = DiagnosticMetadata.read(repository, definitionId, json);
        } catch (IllegalStateException error) {
            // 部署可在实例结束后删除；不能因此让已持久化的变量和活动历史不可读。
            metadata = json.createObjectNode();
        }
        List<Map<String, String>> nodes = new ArrayList<>();
        metadata.path("nodes").elements().forEachRemaining(node -> nodes.add(Map.of(
            "id", node.path("id").asText(), "name", node.path("name").asText())));
        var result = new DefinitionSummary(metadata.path("version").asText(), List.copyOf(nodes));
        synchronized (summaries) {
            summaries.put(definitionId, result);
            if (summaries.size() > 16) summaries.remove(summaries.keySet().iterator().next());
        }
        return result;
    }

    @GetMapping("/diagnosis-api/capabilities")
    public Map<String, Object> capabilities() {
        return Map.of("historyVersion", 1, "recoveryVersion", 1);
    }

    @GetMapping("/diagnosis-api/instances/{instanceId}/recovery")
    @Transactional(readOnly = true)
    public JsonNode recovery(@PathVariable String instanceId) {
        var instance = history.createHistoricProcessInstanceQuery().processInstanceId(instanceId).unfinished().singleResult();
        if (instance == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No active instance / 活动实例不存在");
        try {
            JsonNode metadata = DiagnosticMetadata.read(repository, instance.getProcessDefinitionId(), json);
            if (!metadata.has("bindings")) throw new IllegalStateException("No diagnostic bindings");
            return metadata;
        } catch (Exception error) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No diagnostic definition / 无诊断执行定义");
        }
    }

    @PostMapping("/diagnosis-api/instances/{instanceId}/history")
    @Transactional(readOnly = true)
    public Map<String, Object> get(@PathVariable String instanceId, @RequestBody HistoryRequest request) {
        // 在命令上下文内读取值，只有版本变化的变量才触发大 JSON / 字节数组的反序列化。
        return management.executeCommand(context -> read(instanceId, request));
    }

    private Map<String, Object> read(String instanceId, HistoryRequest request) {
        var process = history.createHistoricProcessInstanceQuery().processInstanceId(instanceId).singleResult();
        if (process == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Unknown process instance / 流程实例不存在");
        Map<String, Object> processState = new LinkedHashMap<>();
        processState.put("id", instanceId);
        processState.put("processDefinitionId", process.getProcessDefinitionId());
        processState.put("startTime", process.getStartTime() == null ? null : process.getStartTime().toInstant().toString());
        processState.put("endTime", process.getEndTime() == null ? null : process.getEndTime().toInstant().toString());
        Map<String, Integer> versions = new LinkedHashMap<>();
        List<Map<String, Object>> variables = new ArrayList<>();
        var query = history.createHistoricVariableInstanceQuery().processInstanceId(instanceId)
            .excludeTaskVariables().orderBy(HISTORY_ID).asc();
        for (int offset = 0; ; offset += 200) {
            if (offset >= 200000) throw new IllegalStateException("Execution history exceeds variable limit / 执行变量超过安全上限");
            var page = query.listPage(offset, 200);
            for (var variable : page) {
                int revision = ((HasRevision) variable).getRevision();
                versions.put(variable.getId(), revision);
                if (request.variables() == null || !Objects.equals(request.variables().get(variable.getId()), revision)) {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("name", variable.getVariableName());
                    value.put("value", variable.getValue());
                    variables.add(Map.of("id", variable.getId(), "variable", value));
                }
            }
            if (page.size() < 200) break;
        }
        Map<String, String> activityVersions = new LinkedHashMap<>();
        Map<String, Map<String, String>> visitedNodes = new LinkedHashMap<>();
        List<Map<String, Object>> activities = new ArrayList<>();
        var activityQuery = history.createHistoricActivityInstanceQuery().processInstanceId(instanceId)
            .orderByHistoricActivityInstanceStartTime().asc().orderBy(HISTORY_ID).asc();
        for (int offset = 0; ; offset += 200) {
            if (offset >= 200000) throw new IllegalStateException("Execution history exceeds activity limit / 活动历史超过安全上限");
            var page = activityQuery.listPage(offset, 200);
            for (var activity : page) {
                visitedNodes.putIfAbsent(activity.getActivityId(), Map.of("id", activity.getActivityId(),
                    "name", activity.getActivityName() == null ? activity.getActivityId() : activity.getActivityName()));
                Map<String, Object> value = new LinkedHashMap<>();
                value.put("id", activity.getId());
                value.put("activityId", activity.getActivityId());
                value.put("activityName", activity.getActivityName());
                value.put("activityType", activity.getActivityType());
                value.put("startTime", activity.getStartTime() == null ? null : activity.getStartTime().toInstant().toString());
                value.put("endTime", activity.getEndTime() == null ? null : activity.getEndTime().toInstant().toString());
                value.put("durationInMillis", activity.getDurationInMillis());
                String version = json.valueToTree(value).toString();
                activityVersions.put(activity.getId(), version);
                if (request.activities() == null || !version.equals(request.activities().get(activity.getId()))) activities.add(value);
            }
            if (page.size() < 200) break;
        }
        var summary = summary(process.getProcessDefinitionId());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("process", processState);
        result.put("nodes", summary.nodes().isEmpty() ? new ArrayList<>(visitedNodes.values()) : summary.nodes());
        result.put("version", summary.version());
        result.put("variableVersions", versions);
        result.put("activityVersions", activityVersions);
        result.put("variables", Map.of("data", variables));
        result.put("activities", Map.of("data", activities));
        result.put("taskIds", tasks.createTaskQuery().processInstanceId(instanceId).active().list().stream().map(task -> task.getId()).sorted().toList());
        return result;
    }
}
