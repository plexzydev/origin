package com.servermc.lobby.cosmetics;

import org.bukkit.Material;

/**
 * Defines all available cosmetic types in Origin Network.
 */
public enum CosmeticType {

    // ═══ Particle Effects ═══
    FLAME_RING("Anillo de Fuego", "§c🔥 Anillo de Fuego", Material.BLAZE_POWDER, CosmeticCategory.PARTICLES, 0),
    ENCHANT_HALO("Halo Encantado", "§b✨ Halo Encantado", Material.ENCHANTED_BOOK, CosmeticCategory.PARTICLES, 100),
    HEART_AURA("Aura de Corazones", "§d❤ Aura de Corazones", Material.APPLE, CosmeticCategory.PARTICLES, 150),
    EMERALD_SPIRAL("Espiral Esmeralda", "§a💎 Espiral Esmeralda", Material.EMERALD, CosmeticCategory.PARTICLES, 200),
    SMOKE_WINGS("Alas de Humo", "§8🦇 Alas de Humo", Material.PHANTOM_MEMBRANE, CosmeticCategory.PARTICLES, 300),
    FLAME_WINGS("Alas de Fuego", "§6🔥 Alas de Fuego", Material.FIRE_CHARGE, CosmeticCategory.PARTICLES, 500),
    ENDER_AURA("Aura del End", "§5🌀 Aura del End", Material.ENDER_PEARL, CosmeticCategory.PARTICLES, 400),
    NOTE_CLOUD("Nube Musical", "§e🎵 Nube Musical", Material.NOTE_BLOCK, CosmeticCategory.PARTICLES, 250),
    SNOW_AURA("Aura de Nieve", "§f❄ Aura de Nieve", Material.SNOWBALL, CosmeticCategory.PARTICLES, 250),
    BLOOD_SPIRAL("Espiral de Sangre", "§4🩸 Espiral de Sangre", Material.REDSTONE, CosmeticCategory.PARTICLES, 350),
    MAGIC_WIND("Viento Mágico", "§d🌪 Viento Mágico", Material.FEATHER, CosmeticCategory.PARTICLES, 300),
    LAVA_RAIN("Lluvia de Lava", "§c🌋 Lluvia de Lava", Material.LAVA_BUCKET, CosmeticCategory.PARTICLES, 450),
    WATER_RINGS("Anillos de Agua", "§3💧 Anillos de Agua", Material.WATER_BUCKET, CosmeticCategory.PARTICLES, 400),
    CHERRY_WIND("Viento de Cerezo", "§d🌸 Viento de Cerezo", Material.CHERRY_SAPLING, CosmeticCategory.PARTICLES, 350),

    // ═══ Mini Pets (Armor Stand followers) ═══
    MINI_CLONE("Mini Clon", "§a👤 Mini Clon", Material.PLAYER_HEAD, CosmeticCategory.PETS, 500),
    MINI_ZOMBIE("Mini Zombie", "§2🧟 Mini Zombie", Material.ZOMBIE_HEAD, CosmeticCategory.PETS, 300),
    MINI_SKELETON("Mini Esqueleto", "§7💀 Mini Esqueleto", Material.SKELETON_SKULL, CosmeticCategory.PETS, 300),
    MINI_CREEPER("Mini Creeper", "§a💣 Mini Creeper", Material.CREEPER_HEAD, CosmeticCategory.PETS, 350),
    MINI_DRAGON("Mini Dragón", "§5🐉 Mini Dragón", Material.DRAGON_HEAD, CosmeticCategory.PETS, 1000),
    MINI_KING("Mini Rey", "§e👑 Mini Rey", Material.GOLDEN_HELMET, CosmeticCategory.PETS, 1200),
    MINI_GHOST("Mini Fantasma", "§f👻 Mini Fantasma", Material.GHAST_TEAR, CosmeticCategory.PETS, 800),
    MINI_NOTCH("Mini Notch", "§e🍎 Mini Notch", Material.GOLDEN_APPLE, CosmeticCategory.PETS, 1500),
    MINI_DEMON("Mini Demonio", "§4😈 Mini Demonio", Material.NETHER_WART, CosmeticCategory.PETS, 900),

    // ═══ Armor Cosmetics ═══
    RAINBOW_ARMOR("Armadura Arcoíris", "§d🌈 Armadura Arcoíris", Material.LEATHER_CHESTPLATE, CosmeticCategory.ARMOR, 2000),
    DISCO_ARMOR("Armadura Disco", "§b🪩 Armadura Disco", Material.JUKEBOX, CosmeticCategory.ARMOR, 1800),
    DARK_KNIGHT("Caballero Oscuro", "§8⚔ Caballero Oscuro", Material.NETHERITE_SCRAP, CosmeticCategory.ARMOR, 800),
    WHITE_KNIGHT("Caballero Blanco", "§f⚔ Caballero Blanco", Material.IRON_INGOT, CosmeticCategory.ARMOR, 800),
    GOLDEN_WARRIOR("Guerrero Dorado", "§6⚔ Guerrero Dorado", Material.GOLD_INGOT, CosmeticCategory.ARMOR, 1000),
    CRIMSON_GUARD("Guardia Carmesí", "§4⚔ Guardia Carmesí", Material.REDSTONE_BLOCK, CosmeticCategory.ARMOR, 900),
    AQUA_DIVER("Buzo Acuático", "§b🌊 Buzo Acuático", Material.PRISMARINE_CRYSTALS, CosmeticCategory.ARMOR, 750),
    FOREST_HUNTER("Cazador del Bosque", "§2🌲 Cazador", Material.OAK_LEAVES, CosmeticCategory.ARMOR, 700);

    private final String name;
    private final String displayName;
    private final Material icon;
    private final CosmeticCategory category;
    private final int price;

    CosmeticType(String name, String displayName, Material icon, CosmeticCategory category, int price) {
        this.name = name;
        this.displayName = displayName;
        this.icon = icon;
        this.category = category;
        this.price = price;
    }

    public String getName() { return name; }
    public String getDisplayName() { return displayName; }
    public Material getIcon() { return icon; }
    public CosmeticCategory getCategory() { return category; }
    public int getPrice() { return price; }

    public enum CosmeticCategory {
        PARTICLES("§6✦ Partículas", Material.BLAZE_POWDER),
        PETS("§a✦ Mascotas", Material.ARMOR_STAND),
        ARMOR("§d✦ Armaduras", Material.LEATHER_CHESTPLATE);

        private final String displayName;
        private final Material icon;

        CosmeticCategory(String displayName, Material icon) {
            this.displayName = displayName;
            this.icon = icon;
        }

        public String getDisplayName() { return displayName; }
        public Material getIcon() { return icon; }
    }
}
