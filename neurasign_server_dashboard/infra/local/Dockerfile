FROM eclipse-temurin:21-jre AS java
FROM node:22-bookworm-slim
COPY --from=java /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:$PATH
ENV CI=true
WORKDIR /app
RUN npm install --global firebase-tools@15.30.2 && mkdir -p /app/state && chown -R node:node /app
COPY --chown=node:node infra/local/firebase.json infra/local/firestore.rules /app/
USER node
RUN firebase setup:emulators:firestore && firebase setup:emulators:ui
EXPOSE 9099 8080 4000
# Export must be a child of the mount: Firebase replaces the export directory.
CMD ["firebase", "emulators:start", "--only", "auth,firestore", "--project", "demo-neurasign", "--config", "/app/firebase.json", "--import", "/app/state/export", "--export-on-exit", "/app/state/export"]
