'use client';

import { useUser } from '@auth0/nextjs-auth0';
import { LogIn, LogOut } from 'lucide-react';
import { clearBearerToken } from '@/lib/authToken';

/** Header auth control: "Log in" link when anonymous, avatar + name +
 *  logout when authenticated. Auth0 routes are served by middleware.ts. */
export default function UserChip() {
  const { user, isLoading } = useUser();

  if (isLoading) return null;

  if (!user) {
    return (
      <a
        href="/auth/login?returnTo=/studio"
        className="px-3 py-1.5 text-sm border border-purple-600 text-purple-600 rounded-lg hover:bg-purple-50 flex items-center gap-1"
      >
        <LogIn className="w-4 h-4" />
        Log in
      </a>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {user.picture && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={user.picture}
          alt=""
          className="w-7 h-7 rounded-full border"
        />
      )}
      <span className="text-sm text-gray-700 max-w-[140px] truncate">
        {user.name || user.email}
      </span>
      <a
        href="/auth/logout"
        onClick={() => clearBearerToken()}
        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        title="Log out"
      >
        <LogOut className="w-4 h-4" />
      </a>
    </div>
  );
}
