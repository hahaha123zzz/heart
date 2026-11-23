"use client";

import Link from "next/link";
import { redirect, usePathname } from "next/navigation";
import SettingsMain from "@/components/settings/SettingsMain";
import {
  ModelCatalogProvider,
  SettingsDraftProvider,
  SettingsProvider,
  UiSettingsProvider,
} from "@/features/settings/store";
import { SettingsAccessProvider, useSettingsAccess } from "@/features/settings/navigation/SettingsAccessProvider";
import { SettingsTourOverlay } from "@/components/settings/SettingsTourOverlay";

export default function SettingsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <SettingsAccessProvider><SettingsContent>{children}</SettingsContent></SettingsAccessProvider>;
}

function SettingsContent({ children }: Readonly<{ children: React.ReactNode }>) {
  const access = useSettingsAccess();
  const pathname = usePathname();
  if (!access.resolved) return <div aria-busy="true">正在读取账号设置…</div>;
  if (access.hideAdminOnly) {
    if (pathname !== "/settings/model") redirect("/settings/model");
    return (
      <main className="min-h-dvh bg-background p-6 text-foreground">
        <Link href="/learning" className="inline-block rounded-md px-3 py-2 text-sm hover:bg-accent">返回我的学习</Link>
        {children}
      </main>
    );
  }
  return (
    <SettingsProvider>
        <UiSettingsProvider>
          <ModelCatalogProvider>
            <SettingsDraftProvider>
              <SettingsMain>{children}</SettingsMain>
              {/* Mounted once at the layout level so the cross-route guided tour
                  survives navigation between the hub and its sub-pages. */}
              <SettingsTourOverlay />
            </SettingsDraftProvider>
          </ModelCatalogProvider>
        </UiSettingsProvider>
    </SettingsProvider>
  );
}
