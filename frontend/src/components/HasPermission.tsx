'use client';

import type { ReactNode } from 'react';

import { useAuthStore } from '@/lib/auth-store';

interface HasPermissionProps {
  permission: string;
  children: ReactNode;
  fallback?: ReactNode;
}

/** 按钮级权限组件：<HasPermission permission="customer:create">...</HasPermission> */
export function HasPermission({ permission, children, fallback = null }: HasPermissionProps) {
  const hasPermission = useAuthStore((s) => s.hasPermission);
  return <>{hasPermission(permission) ? children : fallback}</>;
}

export default HasPermission;
