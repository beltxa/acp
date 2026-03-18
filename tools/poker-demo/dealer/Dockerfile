FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY sdks/java ./sdks/java
COPY tools/poker-demo ./tools/poker-demo

RUN mvn -f sdks/java/pom.xml -DskipTests -Dgpg.skip=true install
RUN mvn -f tools/poker-demo/pom.xml -pl dealer -am -Pproduction -DskipTests package
RUN cp "$(ls -1t /workspace/tools/poker-demo/dealer/target/poker-demo-dealer-*.jar | grep -vE '(original|plain)' | head -n1)" \
  /workspace/tools/poker-demo/dealer/target/app.jar

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/tools/poker-demo/dealer/target/app.jar app.jar

EXPOSE 8090
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
