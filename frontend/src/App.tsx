import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "@/components/Layout";
import { UploadPage } from "@/pages/UploadPage";
import { FilesPage } from "@/pages/FilesPage";
import { ChatPage } from "@/pages/ChatPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 10_000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Layout>
        {(page) => {
          if (page === "upload") return <UploadPage />;
          if (page === "files") return <FilesPage />;
          return <ChatPage />;
        }}
      </Layout>
    </QueryClientProvider>
  );
}
