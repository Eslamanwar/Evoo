{{- define "service.keda.kafka" }}
{{- $Values := .Values }}
{{- if and ($Values.kedaScaling.enabled) ($Values.kedaScaling.trigger.kafka.enabled) }}
- type: kafka
  metadata:
    bootstrapServers: {{ $Values.kedaScaling.trigger.kafka.bootstrapServers | quote }}
    consumerGroup: {{ $Values.kedaScaling.trigger.kafka.consumerGroup | quote }}
    topic: {{ $Values.kedaScaling.trigger.kafka.topic | quote }}
    {{- if $Values.kedaScaling.trigger.kafka.lagThreshold }}
    lagThreshold: {{ $Values.kedaScaling.trigger.kafka.lagThreshold | quote}}
    {{- end }}
    {{- if $Values.kedaScaling.trigger.kafka.offsetResetPolicy }}
    offsetResetPolicy: {{ $Values.kedaScaling.trigger.kafka.offsetResetPolicy | quote}}
    {{- end }}
  authenticationRef:
    name: {{ include "service.fullname" . }}-kafka
  metricType: Value
{{- end }}
{{- end }}
