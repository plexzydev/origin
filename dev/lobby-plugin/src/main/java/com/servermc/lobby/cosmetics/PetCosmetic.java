package com.servermc.lobby.cosmetics;

import com.servermc.lobby.LobbyCore;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.SkullMeta;
import org.bukkit.util.EulerAngle;
import org.bukkit.util.Vector;

/**
 * Pet cosmetic: Mini armor stands that levitate and follow the player.
 * They're small, have heads (player skull or mob head), and orbit around you.
 */
public class PetCosmetic implements Cosmetic {

    private final CosmeticType type;
    private ArmorStand pet;
    private int tickCounter = 0;
    private double orbitAngle = 0;

    // Orbit parameters
    private static final double ORBIT_RADIUS = 1.8;
    private static final double ORBIT_SPEED = 0.08;
    private static final double FLOAT_HEIGHT = 0.8;
    private static final double BOB_AMPLITUDE = 0.15;
    private static final double BOB_SPEED = 0.1;

    public PetCosmetic(CosmeticType type) {
        this.type = type;
    }

    @Override
    public CosmeticType getType() { return type; }

    @Override
    public void equip(Player player) {
        tickCounter = 0;
        orbitAngle = Math.random() * Math.PI * 2; // Random start angle
        spawnPet(player);
    }

    @Override
    public void unequip(Player player) {
        removePet();
    }

    @Override
    public void tick(Player player) {
        tickCounter++;

        if (pet == null || pet.isDead()) {
            spawnPet(player);
            return;
        }

        // Calculate orbit position
        orbitAngle += ORBIT_SPEED;
        if (orbitAngle > Math.PI * 2) orbitAngle -= Math.PI * 2;

        Location playerLoc = player.getLocation();
        double targetX = playerLoc.getX() + ORBIT_RADIUS * Math.cos(orbitAngle);
        double targetZ = playerLoc.getZ() + ORBIT_RADIUS * Math.sin(orbitAngle);
        double bobOffset = BOB_AMPLITUDE * Math.sin(tickCounter * BOB_SPEED);
        double targetY = playerLoc.getY() + FLOAT_HEIGHT + bobOffset;

        Location targetLoc = new Location(player.getWorld(), targetX, targetY, targetZ);

        // Smoothly interpolate current position to target
        Location currentLoc = pet.getLocation();
        double lerpFactor = 0.25; // Smooth follow speed
        double newX = currentLoc.getX() + (targetLoc.getX() - currentLoc.getX()) * lerpFactor;
        double newY = currentLoc.getY() + (targetLoc.getY() - currentLoc.getY()) * lerpFactor;
        double newZ = currentLoc.getZ() + (targetLoc.getZ() - currentLoc.getZ()) * lerpFactor;

        // Face the player
        Location newLoc = new Location(player.getWorld(), newX, newY, newZ);
        Vector direction = playerLoc.toVector().subtract(newLoc.toVector());
        if (direction.lengthSquared() > 0.01) {
            newLoc.setDirection(direction);
        }

        pet.teleport(newLoc);

        // Slight head tilt animation
        double headTilt = Math.sin(tickCounter * 0.15) * 0.2;
        pet.setHeadPose(new EulerAngle(headTilt, 0, 0));
    }

    private void spawnPet(Player player) {
        removePet(); // Clean up any existing pet

        Location loc = player.getLocation().add(ORBIT_RADIUS, FLOAT_HEIGHT, 0);

        pet = player.getWorld().spawn(loc, ArmorStand.class, stand -> {
            stand.setSmall(true);
            stand.setInvisible(true);
            stand.setInvulnerable(true);
            stand.setGravity(false);
            stand.setCanPickupItems(false);
            stand.setBasePlate(false);
            stand.setMarker(false); // Not marker so it has collision box for visual
            stand.setArms(false);
            stand.setCustomNameVisible(false);
            stand.setPersistent(false); // Don't save to disk
            stand.setSilent(true);

            // Set the head based on cosmetic type
            ItemStack helmet = getHelmetForType(player);
            if (helmet != null) {
                stand.getEquipment().setHelmet(helmet);
            }

            // Set colored armor
            org.bukkit.Color armorColor = getColorForType();
            if (armorColor != null) {
                stand.getEquipment().setChestplate(createColoredArmor(Material.LEATHER_CHESTPLATE, armorColor));
                stand.getEquipment().setLeggings(createColoredArmor(Material.LEATHER_LEGGINGS, armorColor));
                stand.getEquipment().setBoots(createColoredArmor(Material.LEATHER_BOOTS, armorColor));
            }
        });
    }

    private ItemStack getHelmetForType(Player player) {
        return switch (type) {
            case MINI_CLONE -> {
                ItemStack skull = new ItemStack(Material.PLAYER_HEAD);
                org.bukkit.inventory.meta.SkullMeta meta = (org.bukkit.inventory.meta.SkullMeta) skull.getItemMeta();
                meta.setOwningPlayer(player);
                skull.setItemMeta(meta);
                yield skull;
            }
            case MINI_ZOMBIE -> new ItemStack(Material.ZOMBIE_HEAD);
            case MINI_SKELETON -> new ItemStack(Material.SKELETON_SKULL);
            case MINI_CREEPER -> new ItemStack(Material.CREEPER_HEAD);
            case MINI_DRAGON -> new ItemStack(Material.DRAGON_HEAD);
            case MINI_KING -> new ItemStack(Material.GOLDEN_HELMET);
            case MINI_GHOST -> {
                ItemStack skull = new ItemStack(Material.PLAYER_HEAD);
                org.bukkit.inventory.meta.SkullMeta meta = (org.bukkit.inventory.meta.SkullMeta) skull.getItemMeta();
                meta.setOwningPlayer(Bukkit.getOfflinePlayer("Ghost"));
                skull.setItemMeta(meta);
                yield skull;
            }
            case MINI_NOTCH -> {
                ItemStack skull = new ItemStack(Material.PLAYER_HEAD);
                org.bukkit.inventory.meta.SkullMeta meta = (org.bukkit.inventory.meta.SkullMeta) skull.getItemMeta();
                meta.setOwningPlayer(Bukkit.getOfflinePlayer("Notch"));
                skull.setItemMeta(meta);
                yield skull;
            }
            case MINI_DEMON -> {
                ItemStack skull = new ItemStack(Material.PLAYER_HEAD);
                org.bukkit.inventory.meta.SkullMeta meta = (org.bukkit.inventory.meta.SkullMeta) skull.getItemMeta();
                meta.setOwningPlayer(Bukkit.getOfflinePlayer("Demon"));
                skull.setItemMeta(meta);
                yield skull;
            }
            default -> null;
        };
    }

    private org.bukkit.Color getColorForType() {
        return switch (type) {
            case MINI_CLONE -> org.bukkit.Color.AQUA;
            case MINI_ZOMBIE -> org.bukkit.Color.GREEN;
            case MINI_SKELETON -> org.bukkit.Color.GRAY;
            case MINI_CREEPER -> org.bukkit.Color.LIME;
            case MINI_DRAGON -> org.bukkit.Color.PURPLE;
            case MINI_KING -> org.bukkit.Color.YELLOW;
            case MINI_GHOST -> org.bukkit.Color.WHITE;
            case MINI_NOTCH -> org.bukkit.Color.ORANGE;
            case MINI_DEMON -> org.bukkit.Color.MAROON;
            default -> null;
        };
    }

    private ItemStack createColoredArmor(Material material, org.bukkit.Color color) {
        ItemStack item = new ItemStack(material);
        org.bukkit.inventory.meta.LeatherArmorMeta meta = (org.bukkit.inventory.meta.LeatherArmorMeta) item.getItemMeta();
        if (meta != null) {
            meta.setColor(color);
            item.setItemMeta(meta);
        }
        return item;
    }

    public void removePet() {
        if (pet != null && !pet.isDead()) {
            pet.remove();
        }
        pet = null;
    }
}
