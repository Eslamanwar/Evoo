{{- define "service.keda.sqs" }}
{{- $Values := .Values }}
{{- if and ($Values.kedaScaling.enabled) ($Values.kedaScaling.trigger.sqs.enabled) }}
- type: aws-sqs-queue
  metadata:
    queueURL: {{ $Values.kedaScaling.trigger.sqs.queueURL |quote }}
    queueLength: {{ $Values.kedaScaling.trigger.sqs.queueLength | default "5" | quote }}
    awsRegion: {{ $Values.kedaScaling.trigger.sqs.awsRegion |quote }}
    {{- if $Values.kedaScaling.trigger.sqs.awsEndpoint }}
    awsEndpoint: {{ $Values.kedaScaling.trigger.sqs.awsEndpoint | quote}}
    {{- end }}
    identityOwner: {{ $Values.kedaScaling.trigger.sqs.identityOwner | default "operator" }}
  metricType: Value
{{- end }}
{{- end }}
