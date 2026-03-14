import fetch from "node-fetch";

/**
 * DataForSEO REST API client
 * Handles authentication and request formatting for DataForSEO v3 API
 */
export class DataForSEOClient {
  constructor(login, password) {
    if (!login || !password) {
      throw new Error("DataForSEO credentials (login and password) are required");
    }

    this.auth = Buffer.from(`${login}:${password}`).toString("base64");
    this.baseURL = "https://api.dataforseo.com/v3";
  }

  /**
   * Make a POST request to DataForSEO API
   * @param {string} endpoint - API endpoint path (e.g., "/serp/google/organic/live/advanced")
   * @param {object} payload - Request payload (will be wrapped in array automatically)
   * @returns {Promise<object>} - API response JSON
   */
  async post(endpoint, payload) {
    try {
      const response = await fetch(`${this.baseURL}${endpoint}`, {
        method: "POST",
        headers: {
          "Authorization": `Basic ${this.auth}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify([payload]) // DataForSEO expects payload as array
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `DataForSEO API error (${response.status}): ${errorText}`
        );
      }

      const result = await response.json();

      // DataForSEO returns {tasks: [...]} structure
      // Validate response structure
      if (!result || !result.tasks || !Array.isArray(result.tasks)) {
        throw new Error("Invalid response structure from DataForSEO API");
      }

      return result;
    } catch (error) {
      // Add context to network errors
      if (error.message.includes("fetch")) {
        throw new Error(`Network error calling DataForSEO API: ${error.message}`);
      }
      throw error;
    }
  }
}
