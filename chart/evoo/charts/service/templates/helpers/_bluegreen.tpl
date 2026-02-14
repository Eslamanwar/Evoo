{{- define "service.rollout.blue-green" }}
{{- $Values := .Values }}
blueGreen:
  {{- if $Values.argoRollouts.rolloutAnalysis.enabled }}
  postPromotionAnalysis: {{- include "service.rollout.analysisBG" . | nindent 4 }}
  {{- end }}
  activeService: {{ include "service.fullname" $ }}
  previewService: {{ include "service.fullname" $ }}-preview
  autoPromotionEnabled: {{ $Values.argoRollouts.autoPromotionEnabled }}
  previewReplicaCount: {{ $Values.argoRollouts.previewReplicaCount | default 1}}
{{- end }}
