import { Moon, Sun } from "lucide-react";
import { Link } from "react-router-dom";
import { useDarkMode } from "@/hooks/useDarkMode";
import { Button } from "@/components/ui/button";
import { Sidebar } from "@/components/Sidebar";
import { AktilotIcon } from "@/components/AktilotIcon";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { dark, toggle } = useDarkMode();

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="shrink-0 z-40 border-b border-border bg-card px-6 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
          <AktilotIcon size={22} />
          <span className="font-semibold text-sm">Aktilot</span>
        </Link>
        <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
