'use client';

import React, { useEffect, useRef, useState } from 'react';

/**
 * Interactive pull-down pendant lamp with real-life physics:
 * - Damped vertical spring bounce (Hooke's law on elastic cord).
 * - True pendulum gravity swing around the ceiling pivot.
 * - 3D torsional cord twist (twist & untwist as it rebounds).
 * - Reliable global pointer release (never gets stuck to cursor).
 * - Solid pitch-black start with full website reveal on pull.
 */
export const AmbientField: React.FC = () => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const lampRef = useRef<HTMLDivElement | null>(null);
  const pendulumRef = useRef<HTMLDivElement | null>(null);
  const interactionRef = useRef<HTMLButtonElement | null>(null);
  // Default to OFF when website starts
  const poweredRef = useRef(false);
  const flickerTimer = useRef<number | null>(null);
  const [powered, setPowered] = useState(false);
  const [flicker, setFlicker] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-lamp', powered ? 'on' : 'off');
    document.body.style.overflow = powered ? '' : 'hidden';
    return () => {
      document.documentElement.removeAttribute('data-lamp');
      document.body.style.overflow = '';
    };
  }, [powered]);

  useEffect(() => {
    const root = rootRef.current;
    const lamp = lampRef.current;
    const pendulum = pendulumRef.current;
    const interaction = interactionRef.current;
    if (!root || !lamp || !pendulum || !interaction) return;

    // Base resting cord length (responsive to viewport)
    let baseLength = Math.max(72, Math.min(115, window.innerHeight * 0.12));
    let pivotX = window.innerWidth / 2;
    const pivotY = 8; // ceiling mount height

    const PULL_THRESHOLD = 26; // px downward pull to trigger toggle
    const MAX_PULL = 85;       // max vertical pull distance in px

    // Physical Degrees of Freedom
    let pullOffset = 0;        // vertical cord stretch (px)
    let pullVelocity = 0;      // vertical velocity (px/frame)

    let angle = 0;             // pendulum swing angle (rad)
    let angularVelocity = 0;   // angular velocity (rad/s)

    let twistAngle = 0;        // 3D cord twist angle (deg)
    let twistVelocity = 0;     // torsional twist velocity (deg/frame)

    let dragging = false;
    let dragPointerId: number | null = null;
    let dragStartY = 0;
    let dragStartTime = 0;
    let didToggle = false;
    let lastDragTime = performance.now();
    let frame = 0;

    const measure = () => {
      baseLength = Math.max(72, Math.min(115, window.innerHeight * 0.12));
      pivotX = window.innerWidth / 2;
      applyVisuals();
    };

    const applyVisuals = () => {
      const totalLength = Math.max(35, baseLength + pullOffset);
      const lengthPx = `${totalLength.toFixed(1)}px`;

      // Update cord length on lamp & ambient containers
      lamp.style.setProperty('--lamp-length', lengthPx);
      root.style.setProperty('--lamp-length', lengthPx);

      // Apply real 2D pendulum swing + 3D cord twist
      pendulum.style.transform = `rotate(${angle.toFixed(5)}rad) rotateY(${twistAngle.toFixed(2)}deg)`;

      // Center hit target along the dynamic 2D swinging arc
      const headX = pivotX + Math.sin(angle) * (totalLength + 14);
      const headY = pivotY + Math.cos(angle) * (totalLength + 14);
      interaction.style.transform = `translate3d(${(headX - 60).toFixed(2)}px, ${(headY - 45).toFixed(2)}px, 0)`;
    };

    applyVisuals();

    const togglePower = () => {
      const next = !poweredRef.current;
      poweredRef.current = next;
      setPowered(next);
      if (next) {
        setFlicker(true);
        if (flickerTimer.current) window.clearTimeout(flickerTimer.current);
        flickerTimer.current = window.setTimeout(() => setFlicker(false), 760);
      }
    };

    /* ---- Pointer & Touch Handlers ---- */

    const onPointerDown = (event: PointerEvent) => {
      dragging = true;
      dragPointerId = event.pointerId;
      dragStartY = event.clientY - pullOffset;
      dragStartTime = performance.now();
      lastDragTime = dragStartTime;
      didToggle = false;
      pullVelocity = 0;
      angularVelocity = 0;
      twistVelocity = 0;

      try {
        interaction.setPointerCapture(event.pointerId);
      } catch (_) {}

      interaction.style.cursor = 'grabbing';
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!dragging) return;

      // Failsafe: if mouse button was released outside, finish immediately
      if (event.buttons === 0) {
        finishDrag();
        return;
      }

      if (dragPointerId !== null && event.pointerId !== dragPointerId) return;

      const now = performance.now();
      const dt = Math.max(8, now - lastDragTime) / 1000;
      lastDragTime = now;

      // 1. Vertical cord pull
      const dy = event.clientY - dragStartY;
      if (dy > 0) {
        if (dy <= 45) {
          pullOffset = dy;
        } else {
          pullOffset = 45 + (dy - 45) * 0.45;
        }
        pullOffset = Math.min(MAX_PULL, pullOffset);
      } else {
        pullOffset = Math.max(-15, dy * 0.25);
      }

      // 2. Lateral pendulum angle
      const dx = event.clientX - pivotX;
      const targetAngle = Math.max(-0.35, Math.min(0.35, Math.atan2(dx, baseLength + pullOffset)));
      const measuredVel = (targetAngle - angle) / dt;
      angularVelocity = 0.65 * measuredVel + 0.35 * angularVelocity;
      angle = targetAngle;

      // 3. Torsional twist while dragging
      const targetTwist = Math.max(-24, Math.min(24, -dx * 0.35 + pullOffset * 0.15));
      twistAngle = targetTwist;

      // Trigger power toggle when crossing threshold
      if (pullOffset >= PULL_THRESHOLD && !didToggle) {
        didToggle = true;
        togglePower();
      }

      applyVisuals();
    };

    const finishDrag = () => {
      if (!dragging) return;

      const elapsed = performance.now() - dragStartTime;
      const isQuickTap = Math.abs(pullOffset) < 8 && elapsed < 320;

      dragging = false;
      dragPointerId = null;
      interaction.style.cursor = 'grab';

      if (isQuickTap && !didToggle) {
        // Quick tap: toggle power and kick off a natural pull, swing, and twist
        togglePower();
        pullOffset = 38;
        pullVelocity = -1.2;
        angularVelocity = (Math.random() > 0.5 ? 1 : -1) * 0.18;
        twistVelocity = (Math.random() > 0.5 ? 1 : -1) * 5.2;
      } else {
        // Drag release: start spring recoil and induce natural twist from release velocity
        pullVelocity = 0;
        twistVelocity = -twistAngle * 0.22;
      }
    };

    /* ---- Real-Life Physics Simulation Loop ---- */

    const tick = () => {
      if (!dragging) {
        let hasMotion = false;

        // 1. Vertical Harmonic Spring (Hooke's law with damping)
        if (Math.abs(pullOffset) > 0.05 || Math.abs(pullVelocity) > 0.05) {
          hasMotion = true;
          const springK = 0.15; // stiffness
          const dampY = 0.82;   // allows 3-4 natural bouncy rebounds
          const forceY = -pullOffset * springK;
          pullVelocity = (pullVelocity + forceY) * dampY;
          pullOffset += pullVelocity;

          if (Math.abs(pullOffset) < 0.05 && Math.abs(pullVelocity) < 0.05) {
            pullOffset = 0;
            pullVelocity = 0;
          }
        }

        // 2. Pendulum Gravity Swing
        if (Math.abs(angle) > 0.001 || Math.abs(angularVelocity) > 0.002) {
          hasMotion = true;
          const effectiveLen = Math.max(0.65, (baseLength + pullOffset) / 100);
          const gravity = 9.81;
          const dampAngle = 0.042; // air and pivot friction

          const accel = -(gravity / effectiveLen) * Math.sin(angle) - dampAngle * angularVelocity;
          angularVelocity += accel * (1 / 60);
          angle += angularVelocity * (1 / 60);

          if (Math.abs(angle) < 0.001 && Math.abs(angularVelocity) < 0.002) {
            angle = 0;
            angularVelocity = 0;
          }
        }

        // 3. 3D Torsional Cord Twist (twisting & untwisting physics)
        if (Math.abs(twistAngle) > 0.05 || Math.abs(twistVelocity) > 0.05) {
          hasMotion = true;
          const twistK = 0.11;  // torsional spring stiffness
          const dampTwist = 0.84; // torsional decay
          // Vertical bouncing and lateral swinging induce subtle torque on the cord
          const twistTorque = -twistAngle * twistK + angle * 14 + pullVelocity * 0.08;
          twistVelocity = (twistVelocity + twistTorque) * dampTwist;
          twistAngle += twistVelocity;

          if (Math.abs(twistAngle) < 0.05 && Math.abs(twistVelocity) < 0.05) {
            twistAngle = 0;
            twistVelocity = 0;
          }
        }

        if (hasMotion) {
          applyVisuals();
        }
      }

      frame = window.requestAnimationFrame(tick);
    };

    frame = window.requestAnimationFrame(tick);

    // Attach pointerdown to the interaction button
    interaction.addEventListener('pointerdown', onPointerDown);

    // Global window listeners guarantee drag ALWAYS releases even if cursor leaves
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    window.addEventListener('pointerup', finishDrag);
    window.addEventListener('pointercancel', finishDrag);
    window.addEventListener('resize', measure);

    return () => {
      window.cancelAnimationFrame(frame);
      interaction.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', finishDrag);
      window.removeEventListener('pointercancel', finishDrag);
      window.removeEventListener('resize', measure);
      if (flickerTimer.current) window.clearTimeout(flickerTimer.current);
    };
  }, []);

  return (
    <>
      {/* Ambient background wash & subtle grid */}
      <div
        className="ambient"
        ref={rootRef}
        data-powered={powered ? 'on' : 'off'}
        data-flicker={flicker ? 'true' : 'false'}
      >
        <div className="ambient__grid" aria-hidden="true" />
        <div className="lamp__wash" aria-hidden="true" />
      </div>

      {/* Cinematic dark veil: shrouds the whole website in pitch darkness until lamp is turned ON */}
      <div
        className="lamp__veil"
        data-off={powered ? 'false' : 'true'}
        aria-hidden="true"
      />

      {/* The Lamp Fixture: positioned at z-index: 65, standing proudly in the dark room */}
      <div
        className="lamp"
        ref={lampRef}
        data-powered={powered ? 'on' : 'off'}
        data-flicker={flicker ? 'true' : 'false'}
        aria-hidden="true"
      >
        <div className="lamp__mount" />
        <div className="lamp__pendulum" ref={pendulumRef}>
          <div className="lamp__glow" />
          <div className="lamp__cone" />
          <div className="lamp__cord" />
          <div className="lamp__shade" />
          <div className="lamp__bulb" />
          <div className="lamp__pull" />
          <div className="lamp__bead" />
        </div>
      </div>

      {/* Elegant floating hint when the lamp is off */}
      {!powered && (
        <div className="lamp__hint" aria-hidden="true">
          ✦ Pull down to turn on ✦
        </div>
      )}

      {/* Primary interaction button - sits over the lamp with grab cursor (z-index: 70) */}
      <button
        ref={interactionRef}
        type="button"
        className="lamp__interaction"
        aria-pressed={powered}
        aria-label={powered ? 'Pull down to turn lamp off' : 'Pull down to turn lamp on'}
        title={powered ? 'Pull down to turn lamp off' : 'Pull down to turn lamp on'}
      />
    </>
  );
};
