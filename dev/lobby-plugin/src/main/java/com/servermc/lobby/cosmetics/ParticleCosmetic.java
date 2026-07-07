package com.servermc.lobby.cosmetics;

import org.bukkit.Color;
import org.bukkit.Location;
import org.bukkit.Particle;
import org.bukkit.entity.Player;

/**
 * Particle-based cosmetics: rings, halos, wings, spirals, auras.
 */
public class ParticleCosmetic implements Cosmetic {

    private final CosmeticType type;
    private int tickCounter = 0;

    public ParticleCosmetic(CosmeticType type) {
        this.type = type;
    }

    @Override
    public CosmeticType getType() { return type; }

    @Override
    public void equip(Player player) {
        tickCounter = 0;
    }

    @Override
    public void unequip(Player player) {
        tickCounter = 0;
    }

    @Override
    public void tick(Player player) {
        tickCounter++;
        Location loc = player.getLocation();

        switch (type) {
            case FLAME_RING -> renderFlameRing(player, loc);
            case ENCHANT_HALO -> renderHalo(player, loc);
            case HEART_AURA -> renderHeartAura(player, loc);
            case EMERALD_SPIRAL -> renderSpiral(player, loc, Particle.HAPPY_VILLAGER);
            case SMOKE_WINGS -> renderWings(player, loc, Particle.LARGE_SMOKE); // Changed to normal smoke so it disappears faster
            case FLAME_WINGS -> renderWings(player, loc, Particle.FLAME);
            case ENDER_AURA -> renderEnderAura(player, loc);
            case NOTE_CLOUD -> renderNoteCloud(player, loc);
            case SNOW_AURA -> renderSnowAura(player, loc);
            case BLOOD_SPIRAL -> renderSpiral(player, loc, Particle.DUST);
            case MAGIC_WIND -> renderSpiral(player, loc, Particle.ENCHANT);
            case LAVA_RAIN -> renderRain(player, loc, Particle.DRIPPING_LAVA);
            case WATER_RINGS -> renderRings(player, loc, Particle.FALLING_WATER);
            case CHERRY_WIND -> renderSpiral(player, loc, Particle.CHERRY_LEAVES);
            default -> {}
        }
    }

    // ═══ FLAME RING: rotating fire ring around player ═══
    private void renderFlameRing(Player player, Location loc) {
        double radius = 1.2;
        double y = loc.getY() + 0.1;
        int points = 20;
        double offset = tickCounter * 0.15;

        for (int i = 0; i < points; i++) {
            double angle = (2 * Math.PI / points) * i + offset;
            double x = loc.getX() + radius * Math.cos(angle);
            double z = loc.getZ() + radius * Math.sin(angle);
            player.getWorld().spawnParticle(Particle.FLAME, x, y, z, 0, 0, 0, 0, 0);
        }
    }

    // ═══ ENCHANT HALO: enchantment particles floating above head ═══
    private void renderHalo(Player player, Location loc) {
        double radius = 0.5;
        double y = loc.getY() + 2.3;
        int points = 16;
        double offset = tickCounter * 0.1;

        for (int i = 0; i < points; i++) {
            double angle = (2 * Math.PI / points) * i + offset;
            double x = loc.getX() + radius * Math.cos(angle);
            double z = loc.getZ() + radius * Math.sin(angle);
            player.getWorld().spawnParticle(Particle.ENCHANT, x, y, z, 0, 0, 0, 0, 0.5);
        }
    }

    // ═══ HEART AURA: hearts float up from player ═══
    private void renderHeartAura(Player player, Location loc) {
        if (tickCounter % 5 != 0) return; // Every 5 ticks
        double x = loc.getX() + (Math.random() - 0.5) * 1.5;
        double y = loc.getY() + 0.5 + Math.random() * 1.5;
        double z = loc.getZ() + (Math.random() - 0.5) * 1.5;
        player.getWorld().spawnParticle(Particle.HEART, x, y, z, 1, 0, 0, 0, 0);
    }

    // ═══ SNOW AURA: snow particles falling around player ═══
    private void renderSnowAura(Player player, Location loc) {
        if (tickCounter % 3 != 0) return;
        double x = loc.getX() + (Math.random() - 0.5) * 2.0;
        double y = loc.getY() + 1.0 + Math.random() * 1.5;
        double z = loc.getZ() + (Math.random() - 0.5) * 2.0;
        player.getWorld().spawnParticle(Particle.ITEM_SNOWBALL, x, y, z, 1, 0, 0, 0, 0);
    }

    // ═══ SPIRAL: spiraling particles ═══
    private void renderSpiral(Player player, Location loc, Particle particle) {
        double radius = 0.8;
        double heightStep = 0.1;
        double offset = tickCounter * 0.3;

        for (int i = 0; i < 10; i++) {
            double angle = offset + i * 0.6;
            double x = loc.getX() + radius * Math.cos(angle);
            double y = loc.getY() + (i * heightStep) + ((tickCounter % 20) * 0.1);
            double z = loc.getZ() + radius * Math.sin(angle);

            if (y > loc.getY() + 2.5) continue;
            
            if (particle == Particle.DUST) {
                // Redstone requires DustOptions
                org.bukkit.Particle.DustOptions dust = new org.bukkit.Particle.DustOptions(org.bukkit.Color.RED, 1.0F);
                player.getWorld().spawnParticle(particle, x, y, z, 0, 0, 0, 0, dust);
            } else {
                player.getWorld().spawnParticle(particle, x, y, z, 0, 0, 0, 0, 0);
            }
        }
    }

    // ═══ WINGS: particle wings behind the player ═══
    private void renderWings(Player player, Location loc, Particle particle) {
        if (tickCounter % 2 != 0) return; // Every 2 ticks for performance

        float yaw = loc.getYaw();
        double radYaw = Math.toRadians(yaw);

        // Wing shape defined as offset points [behindOffset, sideOffset, height]
        double[][] wingPoints = {
            // Left wing
            {-0.3, 0.2, 1.0}, {-0.35, 0.35, 1.2}, {-0.4, 0.5, 1.4},
            {-0.45, 0.65, 1.5}, {-0.4, 0.8, 1.55}, {-0.35, 0.6, 1.7},
            {-0.3, 0.4, 1.8}, {-0.25, 0.2, 1.85},
            {-0.35, 0.3, 0.8}, {-0.4, 0.45, 0.6}, {-0.45, 0.6, 0.5},
            // Right wing
            {-0.3, -0.2, 1.0}, {-0.35, -0.35, 1.2}, {-0.4, -0.5, 1.4},
            {-0.45, -0.65, 1.5}, {-0.4, -0.8, 1.55}, {-0.35, -0.6, 1.7},
            {-0.3, -0.4, 1.8}, {-0.25, -0.2, 1.85},
            {-0.35, -0.3, 0.8}, {-0.4, -0.45, 0.6}, {-0.45, -0.6, 0.5},
        };

        for (double[] point : wingPoints) {
            double behind = point[0];
            double side = point[1];
            double height = point[2];

            // Rotate based on player yaw
            double x = loc.getX() + behind * (-Math.sin(radYaw)) + side * Math.cos(radYaw);
            double y = loc.getY() + height;
            double z = loc.getZ() + behind * Math.cos(radYaw) + side * Math.sin(radYaw);

            player.getWorld().spawnParticle(particle, x, y, z, 0, 0, 0, 0, 0);
        }
    }
    
    // ═══ RAIN: particles dripping from above ═══
    private void renderRain(Player player, Location loc, Particle particle) {
        if (tickCounter % 3 != 0) return;
        for(int i=0; i<3; i++) {
            double x = loc.getX() + (Math.random() - 0.5) * 2.0;
            double y = loc.getY() + 2.5 + Math.random();
            double z = loc.getZ() + (Math.random() - 0.5) * 2.0;
            player.getWorld().spawnParticle(particle, x, y, z, 1, 0, 0, 0, 0);
        }
    }
    
    // ═══ RINGS: Expanding rings ═══
    private void renderRings(Player player, Location loc, Particle particle) {
        if (tickCounter % 15 != 0) return;
        double y = loc.getY() + 0.2;
        int points = 30;
        double radius = (tickCounter % 60) / 20.0 + 0.5; // Expands outward

        for (int i = 0; i < points; i++) {
            double angle = (2 * Math.PI / points) * i;
            double x = loc.getX() + radius * Math.cos(angle);
            double z = loc.getZ() + radius * Math.sin(angle);
            player.getWorld().spawnParticle(particle, x, y, z, 0, 0, 0, 0, 0);
        }
    }

    // ═══ ENDER AURA: portal particles swirling ═══
    private void renderEnderAura(Player player, Location loc) {
        for (int i = 0; i < 3; i++) {
            double x = loc.getX() + (Math.random() - 0.5) * 1.5;
            double y = loc.getY() + Math.random() * 2.0;
            double z = loc.getZ() + (Math.random() - 0.5) * 1.5;
            player.getWorld().spawnParticle(Particle.PORTAL, x, y, z, 0, 0, 0.5, 0, 1.0);
        }
    }

    // ═══ NOTE CLOUD: musical notes around player ═══
    private void renderNoteCloud(Player player, Location loc) {
        if (tickCounter % 4 != 0) return;
        double x = loc.getX() + (Math.random() - 0.5) * 1.5;
        double y = loc.getY() + 1.5 + Math.random() * 0.8;
        double z = loc.getZ() + (Math.random() - 0.5) * 1.5;
        player.getWorld().spawnParticle(Particle.NOTE, x, y, z, 1, 0, 0, 0, 1);
    }
}
