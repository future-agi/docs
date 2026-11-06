plugins {
    kotlin("jvm") version "2.3.10"
    application
}

val koogVersion = providers.gradleProperty("koogVersion").get()
val otelVersion = providers.gradleProperty("otelVersion").get()

repositories {
    mavenCentral()
}

dependencies {
    // Koog umbrella artifact. It already contains the OpenTelemetry feature and the OpenTelemetry Java SDK.
    implementation("ai.koog:koog-agents:$koogVersion")
    // OTLP/HTTP span exporter from the OpenTelemetry Java SDK (same version line as Koog's BOM).
    implementation(platform("io.opentelemetry:opentelemetry-bom:$otelVersion"))
    implementation("io.opentelemetry:opentelemetry-exporter-otlp")

    testImplementation(kotlin("test-junit5"))
    testImplementation("io.opentelemetry:opentelemetry-sdk-testing")
    // Only for the fixture recorder (writes OTLP/JSON instead of sending it).
    testImplementation("io.opentelemetry:opentelemetry-exporter-logging-otlp")
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

application {
    mainClass.set("ai.futureagi.examples.koog.MainKt")
}

// The page's quickstart uses OpenAIModels.Chat.GPT5_6Luna, which is new in Koog 1.3.0.
// Older-version legs (-PkoogVersion=1.2.0) build without it.
if (koogVersion != "1.3.0") {
    kotlin.sourceSets.named("main") { kotlin.exclude("**/quickstart/**") }
}

tasks.test {
    useJUnitPlatform()
    // The tests never call a real model or a real Future AGI endpoint.
    environment.keys.removeIf { it.startsWith("FI_") || it.startsWith("OPENAI_") }
    testLogging { events("passed", "failed", "skipped"); exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL }
}

// Records one real run as an OTLP/JSON fixture (content off). Needs the same env as `run`.
// ./gradlew recordFixture -Pfixture=fixtures/koog-weather.otlp.json
tasks.register<JavaExec>("recordFixture") {
    group = "verification"
    description = "Runs the agent once against the configured model and writes the export as OTLP/JSON."
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("ai.futureagi.examples.koog.RecordFixtureKt")
    args(project.findProperty("fixture")?.toString() ?: "fixtures/koog-weather.otlp.json")
}

// Runs the docs page's quickstart snippet (src/main/kotlin/.../quickstart/Quickstart.kt). Same env as `run`.
tasks.register<JavaExec>("quickstart") {
    group = "application"
    description = "Runs the docs page's quickstart snippet once."
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("ai.futureagi.examples.koog.quickstart.QuickstartKt")
}
