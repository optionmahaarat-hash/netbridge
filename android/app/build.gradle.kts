plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.netbridge.lite"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.netbridge.lite"
        minSdk = 26
        targetSdk = 33            // 33: no foreground-service-type rules for the VPN service
        versionCode = 3
        versionName = "0.2.0"
        ndk { abiFilters += "arm64-v8a" }
    }

    signingConfigs {
        create("release") {
            val ks = System.getenv("KEYSTORE_PATH")
            if (ks != null && file(ks).exists()) {       // CI / your own key: updates install over old versions
                storeFile = file(ks)
                storePassword = System.getenv("KEYSTORE_PASS") ?: "netbridge"
                keyAlias = System.getenv("KEY_ALIAS") ?: "nb"
                keyPassword = System.getenv("KEYSTORE_PASS") ?: "netbridge"
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            val rel = signingConfigs.getByName("release")
            signingConfig = if (rel.storeFile != null) rel else signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    packaging {
        jniLibs {
            useLegacyPackaging = true                       // Xray is started as a program from the native-library folder
            keepDebugSymbols += "**/libxray.so"             // never "strip" the Go binary
        }
    }
    androidResources { noCompress += listOf("dat") }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
