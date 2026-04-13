package rs.prospel.receiptscanner.network

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

interface ProspElApi {
    @FormUrlEncoded
    @POST("api/auth/login")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String,
        @Field("grant_type") grantType: String = "password",
    ): TokenResponse

    @GET("api/projects")
    suspend fun listProjects(
        @Header("Authorization") authorization: String,
        @Query("show_archived") showArchived: Boolean = false,
    ): List<ProjectResponse>

    @POST("api/receipts/import-from-qr")
    suspend fun importReceipt(
        @Header("Authorization") authorization: String,
        @Body body: ReceiptImportRequest,
    ): ReceiptImportResponse

    @POST("api/receipts/{receiptId}/assign-project")
    suspend fun assignProject(
        @Header("Authorization") authorization: String,
        @Path("receiptId") receiptId: Int,
        @Body body: AssignProjectRequest,
    ): ReceiptDetailResponse
}

object ProspElApiFactory {
    fun create(baseUrl: String): ProspElApi {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(40, TimeUnit.SECONDS)
            .writeTimeout(40, TimeUnit.SECONDS)
            .build()

        return Retrofit.Builder()
            .baseUrl(normalizeBaseUrl(baseUrl))
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ProspElApi::class.java)
    }

    fun normalizeBaseUrl(input: String): String {
        var value = input.trim()
        if (value.isBlank()) return "http://192.168.10.20:5173/"
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://$value"
        }
        if (!value.endsWith("/")) value += "/"
        return value
    }
}

