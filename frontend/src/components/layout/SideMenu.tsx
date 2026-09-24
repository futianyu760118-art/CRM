'use client';

import { SettingOutlined } from '@ant-design/icons';
import { Menu } from 'antd';
import type { MenuProps } from 'antd';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { renderIcon } from '@/lib/icons';
import type { MenuItem } from '@/types';

export function buildMenuItems(menus: MenuItem[]): MenuProps['items'] {
  const sorted = [...menus].sort((a, b) => a.sort - b.sort);
  const isChild = (m: MenuItem) => (m.path ?? '').startsWith('/settings/');
  const parent = sorted.find((m) => m.code === 'system:view');

  const items: MenuProps['items'] = sorted
    .filter((m) => !isChild(m) && m.code !== 'system:view')
    .map((m) => ({
      key: m.path ?? m.code,
      icon: renderIcon(m.icon),
      label: m.name,
    }));

  const children = sorted.filter(isChild).map((m) => ({
    key: m.path ?? m.code,
    label: m.name,
  }));

  if (children.length > 0) {
    items.push({
      key: 'settings',
      icon: <SettingOutlined />,
      label: parent?.name ?? '系统设置',
      children,
    });
  }
  return items;
}

export function SideMenu({ menus }: { menus: MenuItem[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const [openKeys, setOpenKeys] = useState<string[]>(['settings']);

  const items = useMemo(() => buildMenuItems(menus), [menus]);

  useEffect(() => {
    if (pathname.startsWith('/settings')) {
      setOpenKeys((keys) => (keys.includes('settings') ? keys : [...keys, 'settings']));
    }
  }, [pathname]);

  return (
    <Menu
      mode="inline"
      theme="dark"
      items={items}
      selectedKeys={[pathname]}
      openKeys={openKeys}
      onOpenChange={setOpenKeys}
      onClick={({ key }) => {
        if (key.startsWith('/')) router.push(key);
      }}
      style={{ borderInlineEnd: 'none' }}
    />
  );
}

export default SideMenu;
