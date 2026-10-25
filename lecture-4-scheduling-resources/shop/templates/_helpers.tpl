{{/* Метки, которых требуют гвардрейлы Kyverno */}}
{{- define "shop.labels" -}}
owner: {{ .Values.labels.owner }}
team: {{ .Values.labels.team }}
environment: {{ .Values.labels.environment }}
{{- end }}

{{/* priorityClassName по ключу из .Values.priorityClasses (critical/standard/batch) */}}
{{- define "shop.priorityClassName" -}}
{{- $root := index . 0 -}}
{{- $key := index . 1 -}}
{{- if and $root.Values.priorityClasses.enabled $key -}}
priorityClassName: {{ (index $root.Values.priorityClasses $key).name }}
{{- end -}}
{{- end }}
