import React from "react";

type StatusAlertTone = "error" | "success";

type StatusAlertProps = {
  tone: StatusAlertTone;
  title: string;
  children: React.ReactNode;
};

const TONE_STYLES: Record<StatusAlertTone, string> = {
  error: "border-red-200 bg-red-50 text-red-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-900",
};

export const StatusAlert: React.FC<StatusAlertProps> = ({ tone, title, children }) => (
  <div className={`rounded-2xl border p-4 text-sm shadow-sm ${TONE_STYLES[tone]}`}>
    <span className="font-semibold">{title}:</span> {children}
  </div>
);
