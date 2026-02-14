{{- define "service.keda.prometheus" }}
{{- $Values := .Values }}
{{- if and ($Values.kedaScaling.enabled) ($Values.kedaScaling.trigger.prometheus.enabled) }}
- type: prometheus
  metadata:
    serverAddress: {{ $Values.kedaScaling.trigger.prometheus.serverAddress | default "http://istio-prometheus-server.istio-system.svc.cluster.local:80" }}
    metricName: istio_request_duration
    query: |
      avg_over_time(
        (
          sum(
            rate(
              istio_request_duration_milliseconds_sum{
                destination_service_namespace="{{ .Release.Namespace }}", destination_service_name=~"{{ include "service.fullname" . }}"
              }[1m]
            )
          )
          /
          sum(
            rate(
              istio_request_duration_milliseconds_count{
                destination_service_namespace="{{ .Release.Namespace }}", destination_service_name=~"{{ include "service.fullname" . }}"
              }[1m]
            )
          )
        )[1m:]
      ) / 1000
    threshold: {{ $Values.kedaScaling.trigger.prometheus.threshold | quote}}
    activationThreshold: {{ $Values.kedaScaling.trigger.prometheus.activationThreshold | default 0 | quote}}
    {{- if $Values.kedaScaling.trigger.prometheus.namespace }}
    namespace: {{ $Values.kedaScaling.trigger.prometheus.namespace | quote}}
    {{- end }}
    {{- if $Values.kedaScaling.trigger.prometheus.cortexOrgID }}
    cortexOrgID: {{ $Values.kedaScaling.trigger.prometheus.cortexOrgID | quote}}
    {{- end }}
    {{- if $Values.kedaScaling.trigger.prometheus.ignoreNullValues }}
    ignoreNullValues: {{ $Values.kedaScaling.trigger.prometheus.ignoreNullValues | default true}}
    {{- end }}
    {{- if $Values.kedaScaling.trigger.prometheus.unsafeSsl }}
    unsafeSsl: {{ $Values.kedaScaling.trigger.prometheus.unsafeSsl | quote}}
    {{- end }}
  metricType: Value
{{- end }}
{{- end }}
