plugins {
    java
}

group = "com.behemoth"
version = "0.1.0"

repositories {
    mavenCentral()
    maven(url = "https://www.dukascopy.com/client/jforexlib/publicrepo/")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    implementation("com.dukascopy.dds2:DDS2-jClient-JForex:3.6.51")

    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.2")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310:2.18.2")
    implementation("io.prometheus:simpleclient:0.16.0")
    implementation("io.prometheus:simpleclient_httpserver:0.16.0")
    implementation("org.duckdb:duckdb_jdbc:1.2.1")
    implementation("org.slf4j:slf4j-api:2.0.16")
    runtimeOnly("ch.qos.logback:logback-classic:1.5.16")

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core:3.27.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
}

tasks.test {
    useJUnitPlatform()
}

tasks.register<JavaExec>("runLocalJForexTester") {
    group = "application"
    description = "Run the local parquet-driven JForex surrogate harness"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("com.behemoth.jforex.LocalJForexTesterRunner")
    workingDir = rootProject.projectDir
    jvmArgs = listOf("-Djava.awt.headless=true")
}

tasks.register<JavaExec>("runJForexTester") {
    group = "application"
    description = "Run the real Dukascopy JForex tester harness"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("com.behemoth.jforex.JForexTesterRunner")
    workingDir = rootProject.projectDir
    jvmArgs = listOf("-Djava.awt.headless=true")
}

tasks.register<JavaExec>("runJForexLive") {
    group = "application"
    description = "Run the Dukascopy JForex live/demo harness"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("com.behemoth.jforex.JForexLiveRunner")
    workingDir = rootProject.projectDir
    jvmArgs = listOf("-Djava.awt.headless=true")
}

tasks.register<JavaExec>("testJForexConnection") {
    group = "application"
    description = "Test the Dukascopy connection credentials from the environment variables"
    classpath = sourceSets.main.get().runtimeClasspath
    mainClass.set("com.behemoth.jforex.JForexConnectionTest")
    workingDir = rootProject.projectDir
    jvmArgs = listOf("-Djava.awt.headless=true")
}
