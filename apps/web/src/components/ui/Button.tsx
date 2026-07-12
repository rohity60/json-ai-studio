'use client';

import { ButtonHTMLAttributes, forwardRef } from 'react';

type Variant = 'primary' | 'secondary' | 'success' | 'danger' | 'ghost' | 'pill' | 'chip';
type Size = 'sm' | 'md' | 'icon';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  /** For `pill` (toggle/tab) buttons: renders the selected state. */
  active?: boolean;
};

const BASE =
  'inline-flex items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-purple-600 text-white hover:bg-purple-700',
  secondary: 'border border-purple-600 text-purple-600 bg-white hover:bg-purple-50',
  success: 'bg-green-600 text-white hover:bg-green-700',
  danger: 'bg-red-600 text-white hover:bg-red-700',
  ghost: 'text-gray-600 hover:bg-gray-100',
  pill: '', // resolved from `active` below
  chip: 'rounded-full border border-purple-200 text-purple-700 bg-purple-50 hover:bg-purple-100 !text-xs',
};

const SIZES: Record<Size, string> = {
  sm: 'px-3 py-1.5',
  md: 'px-4 py-2',
  icon: 'p-1 rounded',
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'sm', active = false, className = '', type = 'button', ...rest },
  ref,
) {
  const variantClasses =
    variant === 'pill'
      ? active
        ? 'bg-purple-100 text-purple-700'
        : 'text-gray-700 hover:bg-gray-100'
      : VARIANTS[variant];

  return (
    <button
      ref={ref}
      type={type}
      className={`${BASE} ${variantClasses} ${SIZES[size]} ${className}`.trim()}
      {...rest}
    />
  );
});

export default Button;
