FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY acp-sdk-java ./acp-sdk-java
COPY tools/poker-demo ./tools/poker-demo

RUN mvn -f acp-sdk-java/pom.xml -DskipTests install
RUN mvn -f tools/poker-demo/pom.xml -pl player -am -DskipTests package
RUN cp "$(ls -1t /workspace/tools/poker-demo/player/target/poker-demo-player-*.jar | grep -vE '(original|plain)' | head -n1)" \
  /workspace/tools/poker-demo/player/target/app.jar

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/tools/poker-demo/player/target/app.jar app.jar

EXPOSE 8091
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
