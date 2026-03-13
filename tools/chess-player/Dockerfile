FROM maven:3.9.11-eclipse-temurin-21 AS build

WORKDIR /workspace

COPY acp-sdk-java ./acp-sdk-java
COPY tools/chess-player ./tools/chess-player

RUN mvn -f acp-sdk-java/pom.xml -DskipTests install
RUN mvn -f tools/chess-player/pom.xml -Pproduction -DskipTests package

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build /workspace/tools/chess-player/target/chess-player-0.1.0.jar /app/chess-player.jar

EXPOSE 8088

ENTRYPOINT ["java", "-jar", "/app/chess-player.jar"]
