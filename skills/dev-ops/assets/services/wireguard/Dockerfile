ARG WG_EASY_BASE_IMAGE=ghcr.io/wg-easy/wg-easy:15.4.0
FROM ${WG_EASY_BASE_IMAGE}

ARG WG_PASSWORD_MIN_LENGTH=8

RUN set -eu; \
    case "${WG_PASSWORD_MIN_LENGTH}" in ''|*[!0-9]*) echo "WG_PASSWORD_MIN_LENGTH must be an integer" >&2; exit 1;; esac; \
    [ "${WG_PASSWORD_MIN_LENGTH}" -ge 8 ]; \
    [ "${WG_PASSWORD_MIN_LENGTH}" -le 128 ]; \
    schema=/app/server/chunks/_/types3.mjs; \
    cli=/app/server/cli.mjs; \
    grep -Fq '.min(12, t("zod.user.password"))' "${schema}"; \
    grep -Fq 'password.length < 12' "${cli}"; \
    grep -Fq 'Password must be at least 12 characters long' "${cli}"; \
    sed -i "s/\\.min(12, t(\"zod.user.password\"))/\\.min(${WG_PASSWORD_MIN_LENGTH}, t(\"zod.user.password\"))/" "${schema}"; \
    sed -i "s/password.length < 12/password.length < ${WG_PASSWORD_MIN_LENGTH}/" "${cli}"; \
    sed -i "s/Password must be at least 12 characters long/Password must be at least ${WG_PASSWORD_MIN_LENGTH} characters long/" "${cli}"; \
    grep -Fq ".min(${WG_PASSWORD_MIN_LENGTH}, t(\"zod.user.password\"))" "${schema}"; \
    grep -Fq "password.length < ${WG_PASSWORD_MIN_LENGTH}" "${cli}"
