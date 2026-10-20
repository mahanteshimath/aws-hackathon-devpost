plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// ./gradlew installDebug -PstartUrl=http://192.168.1.10:5173/
val startUrl: String = (project.findProperty("startUrl") as String?)
    ?: "https://appassets.androidplatform.net/assets/index.html"

android {
    namespace = "dev.firetvkit.shell"
    compileSdk = 35
    defaultConfig {
        applicationId = "dev.firetvkit.shell"
        minSdk = 22
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "START_URL", "\"$startUrl\"")
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.webkit:webkit:1.12.1")
}
