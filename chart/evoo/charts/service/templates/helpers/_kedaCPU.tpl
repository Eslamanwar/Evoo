{{- define "service.keda.cpu" }}
{{- $Values := .Values }}
{{- if and ($Values.kedaScaling.enabled) ($Values.kedaScaling.trigger.cpu.enabled) }}
- type: cpu
  metricType: Utilization
  metadata:
    value: {{ $Values.kedaScaling.trigger.cpu.value |quote }}
    {{- if $Values.kedaScaling.trigger.cpu.containerName }}
    containerName: {{ include "service.fullname" . }}
    {{- end }}
{{- end }}
{{- end }}
