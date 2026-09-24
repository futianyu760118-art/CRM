'use client';

import { Spin } from 'antd';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { useAuthStore } from '@/lib/auth-store';

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const loadUser = useAuthStore((s) => s.loadUser);
  const [mounted, setMounted] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!accessToken) {
      router.replace('/login');
      return;
    }
    if (user) {
      setReady(true);
      return;
    }
    let cancelled = false;
    loadUser().then((loaded) => {
      if (cancelled) return;
      if (!loaded) {
        router.replace('/login');
      } else {
        setReady(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [mounted, accessToken, user, loadUser, router]);

  if (!mounted || !ready) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
