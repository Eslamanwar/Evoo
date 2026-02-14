{{- define "service.rollout.analysisBG" }}
{{- $rolloutAnalysis := .Values.argoRollouts.rolloutAnalysis -}}
templates:
  {{- if $rolloutAnalysis.latency }}
  - templateName: latency
    clusterScope: true
  {{- end }}
  {{- if $rolloutAnalysis.status4xx }}
  - templateName: percentage-4xx
    clusterScope: true
  {{- end }}
  {{- if $rolloutAnalysis.status5xx }}
  - templateName: percentage-5xx
    clusterScope: true
  {{- end }}
  {{- if $rolloutAnalysis.newRelicAnomalies }}
  - templateName: newrelic-aiops
    clusterScope: true
  {{- end }}
  {{- if $rolloutAnalysis.customAnalysis.enabled }}
  - templateName: custom-newrelic-analysis
    clusterScope: true
  {{- end }}
args:
  - name: serviceName
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: canary-pod-hash
    valueFrom:
      podTemplateHashValue: Latest
  - name: since
    value: {{ ($rolloutAnalysis.measurementDuration | default "30" | quote) }}
  {{- if $rolloutAnalysis.enabled }}
  - name: appName
    value: {{ $rolloutAnalysis.newRelicAnomalies.appName | default (include "service.fullname" $) }}
  {{- end }}
  {{- if $rolloutAnalysis.status4xx }}
  - name: 4xxThreshold
    value: {{ $rolloutAnalysis.status4xx.failurePercentageThreshold | quote }}
  {{- end }}
  {{- if $rolloutAnalysis.status5xx }}
  - name: 5xxThreshold
    value: {{ $rolloutAnalysis.status5xx.failurePercentageThreshold | quote }}
  {{- end }}
  {{- if $rolloutAnalysis.latency }}
  - name: latencyThreshold
    value: {{ $rolloutAnalysis.latency | quote }}
  {{- end }}
  {{- if $rolloutAnalysis.customAnalysis.enabled }}
  - name: threshold
    value: {{ $rolloutAnalysis.customAnalysis.threshold | quote }}
  - name: query
    value: {{ $rolloutAnalysis.customAnalysis.query | quote }}
  {{- end }}
{{- end }}
