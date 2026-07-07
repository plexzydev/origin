package com.servermc.lobby.cosmetics;

import org.bukkit.Color;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.LeatherArmorMeta;

public class ArmorCosmetic implements Cosmetic {

    private final CosmeticType type;
    private int tickCounter = 0;
    
    // For Rainbow effect
    private float hue = 0f;

    public ArmorCosmetic(CosmeticType type) {
        this.type = type;
    }

    @Override
    public CosmeticType getType() {
        return type;
    }

    @Override
    public void equip(Player player) {
        tickCounter = 0;
        updateArmor(player);
    }

    @Override
    public void unequip(Player player) {
        player.getInventory().setChestplate(null);
        player.getInventory().setLeggings(null);
        player.getInventory().setBoots(null);
    }

    @Override
    public void tick(Player player) {
        tickCounter++;
        
        if (type == CosmeticType.RAINBOW_ARMOR) {
            hue += 0.02f;
            if (hue > 1.0f) hue = 0f;
            
            java.awt.Color awtColor = java.awt.Color.getHSBColor(hue, 1.0f, 1.0f);
            Color color = Color.fromRGB(awtColor.getRed(), awtColor.getGreen(), awtColor.getBlue());
            setArmorColors(player, color);
            return;
        }
        
        if (type == CosmeticType.DISCO_ARMOR) {
            if (tickCounter % 10 == 0) { // Every half second
                Color color = Color.fromRGB(
                    (int)(Math.random() * 255), 
                    (int)(Math.random() * 255), 
                    (int)(Math.random() * 255)
                );
                setArmorColors(player, color);
            }
            return;
        }
        
        // Static armors don't need ticking, but we can re-apply them just in case
        if (tickCounter % 100 == 0) {
            updateArmor(player);
        }
    }
    
    private void updateArmor(Player player) {
        if (type == CosmeticType.RAINBOW_ARMOR || type == CosmeticType.DISCO_ARMOR) return;
        
        Color color = switch(type) {
            case DARK_KNIGHT -> Color.BLACK;
            case WHITE_KNIGHT -> Color.WHITE;
            case GOLDEN_WARRIOR -> Color.YELLOW;
            case CRIMSON_GUARD -> Color.MAROON;
            case AQUA_DIVER -> Color.AQUA;
            case FOREST_HUNTER -> Color.GREEN;
            default -> Color.GRAY;
        };
        
        setArmorColors(player, color);
    }
    
    private void setArmorColors(Player player, Color color) {
        player.getInventory().setChestplate(createColoredArmor(Material.LEATHER_CHESTPLATE, color));
        player.getInventory().setLeggings(createColoredArmor(Material.LEATHER_LEGGINGS, color));
        player.getInventory().setBoots(createColoredArmor(Material.LEATHER_BOOTS, color));
    }
    
    private ItemStack createColoredArmor(Material material, Color color) {
        ItemStack item = new ItemStack(material);
        LeatherArmorMeta meta = (LeatherArmorMeta) item.getItemMeta();
        if (meta != null) {
            meta.setColor(color);
            // Hide the dye attributes and add enchant glint
            meta.addEnchant(org.bukkit.enchantments.Enchantment.UNBREAKING, 1, true);
            meta.addItemFlags(org.bukkit.inventory.ItemFlag.HIDE_DYE, org.bukkit.inventory.ItemFlag.HIDE_ENCHANTS);
            item.setItemMeta(meta);
        }
        return item;
    }
}
