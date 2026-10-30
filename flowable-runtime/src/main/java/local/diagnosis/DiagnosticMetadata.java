package local.diagnosis;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.flowable.engine.RepositoryService;

/** 旧部署把元数据放在说明字段；执行、复核和历史必须使用同一个读取规则。 */
final class DiagnosticMetadata {
    private DiagnosticMetadata() {}

    static JsonNode read(RepositoryService repository, String definitionId, ObjectMapper json) {
        try {
            var process = repository.getBpmnModel(definitionId).getMainProcess();
            var extensions = process.getExtensionElements().get("diagnosticExecution");
            if (extensions != null && !extensions.isEmpty()) {
                return json.readTree(extensions.get(0).getAttributes().get("value").get(0).getValue());
            }
            return process.getDocumentation() == null ? json.createObjectNode()
                : json.readTree(process.getDocumentation()).path("diagnosticExecution");
        } catch (Exception error) {
            throw new IllegalStateException("Invalid diagnostic execution metadata", error);
        }
    }
}
