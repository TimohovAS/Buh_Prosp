package rs.prospel.receiptscanner.network

import com.google.gson.annotations.SerializedName
import java.math.BigDecimal

data class TokenResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer",
    val user: UserResponse,
)

data class UserResponse(
    val id: Int,
    val username: String,
    @SerializedName("full_name") val fullName: String?,
    val role: String,
)

data class ProjectResponse(
    val id: Int,
    val name: String,
    val code: String? = null,
    val status: String? = null,
    @SerializedName("client_name") val clientName: String? = null,
)

data class ReceiptImportRequest(
    @SerializedName("verification_url") val verificationUrl: String,
)

data class ReceiptImportResponse(
    val created: Boolean,
    val receipt: ReceiptDetailResponse,
)

data class ReceiptDetailResponse(
    val id: Int,
    @SerializedName("invoice_number") val invoiceNumber: String? = null,
    @SerializedName("seller_name") val sellerName: String? = null,
    @SerializedName("payment_type") val paymentType: String? = null,
    @SerializedName("total_amount") val totalAmount: BigDecimal = BigDecimal.ZERO,
    val currency: String = "RSD",
    @SerializedName("project_name") val projectName: String? = null,
    val status: String = "new",
    val items: List<ReceiptItemResponse> = emptyList(),
)

data class ReceiptItemResponse(
    val id: Int,
    @SerializedName("line_no") val lineNo: Int,
    val name: String,
    val quantity: BigDecimal = BigDecimal.ZERO,
    @SerializedName("unit_price") val unitPrice: BigDecimal = BigDecimal.ZERO,
    @SerializedName("total_amount") val totalAmount: BigDecimal = BigDecimal.ZERO,
)

data class AssignProjectRequest(
    @SerializedName("project_id") val projectId: Int?,
)

