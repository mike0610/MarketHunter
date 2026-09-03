import axios from "axios";

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
});

export async function getExperiment1State() {
    const response = await api.get("/experiment1/state");
    return response.data;
}

export default api;
