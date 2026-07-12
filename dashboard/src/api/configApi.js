import axios from "axios";

const api = axios.create({
    baseURL: (
        import.meta.env.VITE_API_BASE_URL
        || "http://127.0.0.1:8000"
    ),
});

export async function getConfig() {
    const response = await api.get(
        "/config",
    );

    return response.data;
}

export default api;
