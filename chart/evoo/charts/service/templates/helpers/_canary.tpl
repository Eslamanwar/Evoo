{{- define "service.rollout.canary" }}
{{- $Values := .Values }}
canary:
  {{- if $Values.istio.enabled }}
  {{- if $Values.argoRollouts.dynamicStableScale }}
  dynamicStableScale: true
  {{- end }}
  {{- if $Values.argoRollouts.abortScaleDownDelaySeconds }}
  abortScaleDownDelaySeconds: {{ $Values.argoRollouts.abortScaleDownDelaySeconds }}
  {{- end }}
  stableService: {{ include "service.fullname" . }}
  canaryService: {{ include "service.fullname" . }}-preview
  trafficRouting:
    istio:
      virtualService:
        name: {{ include "service.fullname" . }}
        routes:
        - primary
  {{- end }}
  {{- if $Values.argoRollouts.rolloutAnalysis.enabled }}
  analysis: {{- include "service.rollout.analysisCanary" . | nindent 4 }}
  {{- end }}
  steps: {{- $Values.argoRollouts.steps | nindent 4 }}
{{- end }}
