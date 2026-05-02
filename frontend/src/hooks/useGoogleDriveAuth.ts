import { useEffect, useState, useRef } from "react";
import { getDriveAuthStatus, loginGoogleDrive, logoutGoogleDrive } from "../api/driveApi";
import type { DriveAuthStatusResponse } from "../types/drive.types";

export function useGoogleDriveAuth() {
  const [authStatus, setAuthStatus] = useState<DriveAuthStatusResponse | null>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const isActionInProgress = useRef(false);

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
    if (isActionInProgress.current) return;
    isActionInProgress.current = true;
    setIsSigningIn(true);
    try {
      const next = await loginGoogleDrive();
      setAuthStatus(next);
      return next;
    } finally {
      setIsSigningIn(false);
      isActionInProgress.current = false;
    }
  };

  const signOut = async () => {
    if (isActionInProgress.current) return;
    isActionInProgress.current = true;
    setIsSigningOut(true);
    try {
      const next = await logoutGoogleDrive();
      setAuthStatus(next);
      return next;
    } finally {
      setIsSigningOut(false);
      isActionInProgress.current = false;
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
