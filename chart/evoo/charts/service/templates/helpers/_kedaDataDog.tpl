{{- define "service.keda.datadog" }}
{{- $Values := .Values }}
{{- if and ($Values.kedaScaling.enabled) ($Values.kedaScaling.trigger.datadog.enabled) }}
- type: datadog
  metadata:
  {{- if $Values.kedaScaling.trigger.datadog.datadogAppName }}
    query: sum:trace.http.request.duration{env:{{ $Values.env }},service:{{ $Values.kedaScaling.trigger.datadog.datadogAppName }}}.rollup(sum).fill(zero).as_rate()
  {{- end }}
    queryValue: {{ $Values.kedaScaling.trigger.datadog.queryValue |quote }}
    age: {{ $Values.kedaScaling.trigger.datadog.age |quote }}
    metricUnavailableValue: {{ $Values.kedaScaling.trigger.datadog.metricUnavailableValue |default 0 |quote }}
    timeWindowOffset: {{ $Values.kedaScaling.trigger.datadog.timeWindowOffset |default 30 |quote }}
    lastAvailablePointOffset: {{ $Values.kedaScaling.trigger.datadog.lastAvailablePointOffset |default 0 |quote }}
  authenticationRef:
    name: {{ include "service.fullname" . }}-datadog
  metricType: AverageValue
{{- end }}
{{- end }}
