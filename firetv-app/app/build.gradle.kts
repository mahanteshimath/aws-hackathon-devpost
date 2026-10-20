plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Where the TV app loads from. Default: the copy bundled in the APK (offline sample story).
//   ./gradlew installDebug -PcrayonUrl=http://192.168.1.10:8787/tv/
//   ./gradlew assembleRelease -PcrayonUrl=https://<your-lambda-url>/tv/
val crayonUrl: String = (project.findProperty("crayonUrl") as String?)
    ?: "https://appassets.androidplatform.net/assets/tv/index.html"

// Bundle the web app (../web) into the APK so it works offline.
val webDir = rootProject.layout.projectDirectory.dir("../web")
val bundledWeb = layout.buildDirectory.dir("generated/crayonWeb")
val copyWeb by tasks.registering(Sync::class) {
    from(webDir)
    into(bundledWeb)
}

android {
    namespace = "com.crayoncinema.tv"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.crayoncinema.tv"
        minSdk = 22 // Fire OS 5+
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "START_URL", "\"$crayonUrl\"")
    }

    buildFeatures { buildConfig = true }

    signingConfigs {
        // Judges/sideloading: release is signed with the debug key unless a keystore is supplied.
        getByName("debug")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    sourceSets["main"].assets.srcDir(bundledWeb)

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

tasks.named("preBuild") { dependsOn(copyWeb) }

dependencies {
    implementation("androidx.webkit:webkit:1.12.1")
}
