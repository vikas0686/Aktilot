import { useState } from "react";
import { Upload, Files, MessageSquare, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDarkMode } from "@/hooks/useDarkMode";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { id: "upload", label: "Documents", icon: Upload },
  { id: "files", label: "Context Files", icon: Files },
  { id: "chat", label: "Chat Assistant", icon: MessageSquare },
] as const;

type Page = (typeof NAV_ITEMS)[number]["id"];

interface LayoutProps {
  children: (page: Page) => React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [page, setPage] = useState<Page>("upload");
  const { dark, toggle } = useDarkMode();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Left Nav */}
      <aside className="flex w-56 flex-col border-r border-border bg-card">
        <div className="flex items-center gap-2 px-4 py-5 border-b border-border">
          <MessageSquare className="h-5 w-5 text-primary" />
          <span className="font-semibold text-sm">Doc AI Assistant</span>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                page === id
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <Button variant="ghost" size="sm" onClick={toggle} className="w-full justify-start gap-2">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {dark ? "Light Mode" : "Dark Mode"}
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">{children(page)}</main>
    </div>
  );
}
