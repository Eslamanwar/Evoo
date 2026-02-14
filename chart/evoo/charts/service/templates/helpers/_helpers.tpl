{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "service.partOf" -}}
{{- if $.Values.partOf }}
{{- $.Values.partOf }}
{{- end }}
{{- end }}

{{/*
Expand the name of the chart.
*/}}
{{- define "service.name" -}}
{{- default $.Chart.Name (tpl $.Values.nameOverride $) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "service.fullname" -}}
{{- if $.Values.fullnameOverride }}
{{- $.Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $.Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "service.chart" -}}
{{- printf "%s-%s" $.Chart.Name $.Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
The same full name as above, but 100% backward compatible (no trim in the default case).
*/}}
{{- define "service.instanceName" -}}
{{- if $.Values.fullnameOverride }}
{{- $.Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $.Release.Name }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "service.labels" -}}
{{- $partOf := include "service.partOf" . -}}
helm.sh/chart: {{ include "service.chart" . }}
dh_env: {{ $.Values.env }}
dh_app: {{ $partOf | default (include "service.name" .) }}
dh_squad: {{ $.Values.squad | default $.Release.Namespace }}
dh_tribe: {{ $.Values.tribe }}
{{ include "service.selectorLabels" . }}
{{- if $.Chart.AppVersion }}
app.kubernetes.io/version: {{ $.Chart.AppVersion | quote }}
{{- end }}
{{- if $partOf }}
app.kubernetes.io/partOf: {{ $partOf }}
{{- end }}
app.kubernetes.io/managed-by: {{ $.Release.Service }}
{{- end }}

{{/*
Additional labels
*/}}
{{- define "service.additionalLabels" -}}
{{- $partOf := include "service.partOf" . -}}
dh_env: {{ $.Values.env }}
dh_app: {{ $partOf | default (include "service.name" .) }}
dh_squad: {{ $.Values.squad | default $.Release.Namespace }}
dh_tribe: {{ $.Values.tribe }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "service.name" . }}
app.kubernetes.io/instance: {{ include "service.instanceName" . }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "service.serviceAccountName" -}}
{{- if $.Values.serviceAccount.create }}
{{- default (include "service.fullname" .) $.Values.serviceAccount.name }}
{{- else }}
{{- default "default" $.Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the external secret to use
*/}}
{{- define "service.externalSecretName" -}}
{{- if $.Values.externalSecret.enabled }}
{{- default (include "service.fullname" .) (tpl $.Values.externalSecret.name $) }}
{{- else }}
{{- default "default" (tpl $.Values.externalSecret.name $) }}
{{- end }}
{{- end }}
