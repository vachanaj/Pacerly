FROM quay.io/keycloak/keycloak:26.2 AS builder

ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_DB=postgres
ENV KC_HTTP_RELATIVE_PATH=/auth

WORKDIR /opt/keycloak
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.2
COPY --from=builder /opt/keycloak/ /opt/keycloak/

# Bake realm configuration into the Keycloak import directory
COPY realm-pacerly.json /opt/keycloak/data/import/realm-pacerly.json

USER 1000
EXPOSE 8080 9000

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]