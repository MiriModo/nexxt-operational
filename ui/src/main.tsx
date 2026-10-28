import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/latin-ext-500.css";
import "@fontsource/wix-madefor-text/400.css";
import "@fontsource/wix-madefor-text/500.css";
import "@fontsource/wix-madefor-text/latin-ext-400.css";
import "@fontsource/wix-madefor-text/latin-ext-500.css";
import "@fontsource/fragment-mono/400.css";
import "@fontsource/fragment-mono/latin-ext-400.css";
import App from "./App";
import { AuthProvider } from "./auth";
import { ToastProvider } from "./components/Toast";
import "./styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
