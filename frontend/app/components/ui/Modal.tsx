"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  maxWidth?: string;
}

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  maxWidth = "max-w-4xl",
}: ModalProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className={`relative w-full ${maxWidth} max-h-[90vh] flex flex-col bg-[#0a0a0a] border border-white/10 rounded-2xl shadow-2xl overflow-hidden`}
          >
            {/* Header */}
            {(title || description) && (
              <div className="flex-none px-6 py-4 border-b border-white/5 bg-white/[0.02]">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    {title && (
                      <h2 className="text-lg font-semibold text-white">
                        {title}
                      </h2>
                    )}
                    {description && (
                      <p className="text-sm text-gray-400 mt-1">
                        {description}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={onClose}
                    className="p-2 -mr-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
            )}
            
            {!title && !description && (
              <button
                onClick={onClose}
                className="absolute top-4 right-4 z-10 p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            )}

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto min-h-0 custom-scrollbar">
              {children}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
