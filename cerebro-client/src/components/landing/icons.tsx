export type IconComponent = (props: { className?: string }) => JSX.Element;

export const TelegramIcon: IconComponent = ({ className }) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <path
      d="M21.4 3.6 2.9 10.9c-1 .4-1 1.5.1 1.8l4.6 1.4 1.8 5.6c.2.7 1.1.9 1.6.3l2.5-2.8 4.7 3.5c.7.5 1.7.1 1.9-.7l3-16.4c.2-1-.8-1.7-1.7-1z"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
    />
    <path
      d="M8.6 14.2 17 7.8 10.5 15l-.2 3.5-1.7-4.3Z"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinejoin="round"
    />
  </svg>
);

export const EmailIcon: IconComponent = ({ className }) => (
  <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
    <rect x="2.5" y="5" width="19" height="14" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
    <path
      d="m3.5 6.5 8.5 6.5 8.5-6.5"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
