{{- define "papervault.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "papervault.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "papervault.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "papervault.labels" -}}
helm.sh/chart: {{ include "papervault.chart" . }}
app.kubernetes.io/name: {{ include "papervault.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "papervault.selectorLabels" -}}
app.kubernetes.io/name: {{ include "papervault.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "papervault.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "papervault.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "papervault.secretName" -}}
{{- default (printf "%s-secret" (include "papervault.fullname" .)) .Values.secret.existingSecret -}}
{{- end -}}

{{- define "papervault.configMapName" -}}
{{- printf "%s-config" (include "papervault.fullname" .) -}}
{{- end -}}
