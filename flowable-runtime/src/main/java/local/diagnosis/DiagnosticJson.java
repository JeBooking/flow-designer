package local.diagnosis;

import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;

/** 引擎元数据可能携带已校验参考文件；只调整内部读取器，不放宽所有 HTTP JSON 请求。 */
final class DiagnosticJson {
    private DiagnosticJson() {}

    static ObjectMapper configure(ObjectMapper source) {
        ObjectMapper mapper = source.copy();
        mapper.getFactory().setStreamReadConstraints(StreamReadConstraints.builder()
            .maxStringLength(70 * 1024 * 1024).build());
        return mapper;
    }
}
