{{- define "service.keda.newRelic" }}
{{- $Values := .Values }}
{{- if and ($Values.kedaScaling.enabled) ($Values.kedaScaling.trigger.newRelic.enabled) }}
{{- $DefaultNrql := print "FROM Transaction SELECT average(duration) as latency where appName like '" $Values.kedaScaling.trigger.newRelic.newRelicAppName "%' since 20 seconds ago" }}
- type: new-relic
  metadata:
    account: {{ $Values.kedaScaling.trigger.newRelic.account |quote }}
    region: {{ $Values.kedaScaling.trigger.newRelic.region | default "US" }}
    noDataError: "{{ $Values.kedaScaling.trigger.newRelic.noDataError | default true }}"
    nrql: {{ $Values.kedaScaling.trigger.newRelic.nrql | default $DefaultNrql |quote}}
    threshold: {{ $Values.kedaScaling.trigger.newRelic.threshold |quote }}
    activationThreshold: {{ $Values.kedaScaling.trigger.newRelic.activationThreshold | default 0 | quote }}
  authenticationRef:
    name: {{ include "service.fullname" . }}-newrelic
  metricType: {{ $Values.kedaScaling.trigger.newRelic.metricType | default "Value" }}
{{- end }}
{{- end }}
