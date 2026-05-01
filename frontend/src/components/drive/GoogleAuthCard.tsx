import React from "react";
import type { DriveAuthStatusResponse } from "../../types/drive.types";

type GoogleAuthCardProps = {
  authStatus: DriveAuthStatusResponse | null;
  description: string;
  helperText: string;
  isSigningIn: boolean;
  isSigningOut: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
};

export const GoogleAuthCard: React.FC<GoogleAuthCardProps> = ({
  authStatus,
  description,
  helperText,
  isSigningIn,
  isSigningOut,
  onSignIn,
  onSignOut,
}) => {
  const ready = Boolean(authStatus?.token_valid);
  const configured = Boolean(authStatus?.configured);
  const showSignOut = configured && Boolean(authStatus?.token_exists);

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Google account</h2>
          <p className="mt-1 text-sm text-slate-600">{authStatus?.message || description}</p>
          <p className="mt-1 text-xs text-slate-500">{helperText}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!configured || isSigningIn || isSigningOut}
            onClick={onSignIn}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {isSigningIn ? "Opening Google..." : ready ? "Refresh sign-in" : "Sign in with Google"}
          </button>
          {showSignOut && (
            <button
              type="button"
              disabled={isSigningIn || isSigningOut}
              onClick={onSignOut}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSigningOut ? "Signing out..." : "Sign out"}
            </button>
          )}
        </div>
      </div>
    </section>
  );
};
