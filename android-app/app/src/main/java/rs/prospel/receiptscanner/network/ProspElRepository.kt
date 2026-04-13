package rs.prospel.receiptscanner.network

class ProspElRepository {
    suspend fun login(baseUrl: String, username: String, password: String): TokenResponse {
        return ProspElApiFactory.create(baseUrl).login(username, password)
    }

    suspend fun listProjects(baseUrl: String, token: String): List<ProjectResponse> {
        return ProspElApiFactory.create(baseUrl).listProjects("Bearer $token")
    }

    suspend fun importReceipt(baseUrl: String, token: String, verificationUrl: String): ReceiptImportResponse {
        return ProspElApiFactory.create(baseUrl).importReceipt(
            authorization = "Bearer $token",
            body = ReceiptImportRequest(verificationUrl = verificationUrl),
        )
    }

    suspend fun assignProject(baseUrl: String, token: String, receiptId: Int, projectId: Int?): ReceiptDetailResponse {
        return ProspElApiFactory.create(baseUrl).assignProject(
            authorization = "Bearer $token",
            receiptId = receiptId,
            body = AssignProjectRequest(projectId = projectId),
        )
    }
}

