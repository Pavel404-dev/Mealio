plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Opt in only for the CI QA build. Never modify the default debug configuration:
// local debug and the existing release configuration still use that configuration.
val qaSigningEnabled = providers.environmentVariable("MEALIO_QA_SIGNING").orNull.let {
    require(it == null || it == "true") { "MEALIO_QA_SIGNING must be true or unset" }
    it == "true"
}
fun qaSigningValue(name: String): String =
    providers.environmentVariable(name).orNull?.takeIf { it.isNotEmpty() }
        ?: throw GradleException("Missing required QA signing setting: $name")

android {
    namespace = "com.mealio.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.mealio.app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    if (qaSigningEnabled) {
        signingConfigs.create("stagingQa") {
            storeFile = file(qaSigningValue("MEALIO_QA_KEYSTORE_PATH"))
            require(storeFile!!.isFile) { "QA keystore is unavailable" }
            storeType = "JKS"
            storePassword = qaSigningValue("ANDROID_QA_STORE_PASSWORD")
            keyAlias = qaSigningValue("ANDROID_QA_KEY_ALIAS")
            keyPassword = qaSigningValue("ANDROID_QA_KEY_PASSWORD")
        }
    }

    buildTypes {
        debug {
            if (qaSigningEnabled) {
                signingConfig = signingConfigs.getByName("stagingQa")
            }
        }
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
