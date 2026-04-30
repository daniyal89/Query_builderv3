import { useEffect, useState } from "react";
import { getDriveAuthStatus, loginGoogleDrive, logoutGoogleDrive } from "../api/driveApi";
import type { DriveAuthStatusResponse } from "../types/drive.types";

export function useGoogleDriveAuth() {
  const [authStatus, setAuthStatus] = useState<DriveAuthStatusResponse | null>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getDriveAuthStatus()
      .then((next) => {
        if (!cancelled) {
          setAuthStatus(next);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshAuthStatus = async () => {
    const next = await getDriveAuthStatus();
    setAuthStatus(next);
    return next;
  };

  const signIn = async () => {
    setIsSigningIn(true);
    try {
      const next = await loginGoogleDrive();
      setAuthStatus(next);
      return next;
    } finally {
      setIsSigningIn(false);
    }
  };

  const signOut = async () => {
    setIsSigningOut(true);
    try {
      const next = await logoutGoogleDrive();
      setAuthStatus(next);
      return next;
    } finally {
      setIsSigningOut(false);
    }
  };

  return {
    authStatus,
    isSigningIn,
    isSigningOut,
    refreshAuthStatus,
    signIn,
    signOut,
  };
}
