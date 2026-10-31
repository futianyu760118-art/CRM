'use client';

import { AntdRegistry } from '@ant-design/nextjs-registry';
import { QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useState, type ReactNode } from 'react';

import { makeQueryClient } from '@/lib/query-client';

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(makeQueryClient);

  return (
    <AntdRegistry>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider
          locale={zhCN}
          theme={{
            token: { colorPrimary: '#1677ff', borderRadius: 4 },
          }}
        >
          <AntApp>{children}</AntApp>
        </ConfigProvider>
      </QueryClientProvider>
    </AntdRegistry>
  );
}

export default Providers;
